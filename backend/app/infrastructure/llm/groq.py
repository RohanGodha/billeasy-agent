"""Groq adapter — Llama 3.3 70B Versatile. Used for parallel WhatsApp drafting + failover."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.observability import get_logger
from app.settings import get_settings

from .base import LLMClient, LLMMessage, LLMResponse

logger = get_logger(__name__)

# Free-tier limit for llama-3.3-70b is ~30 RPM; stay under it.
_MAX_RPM = 24


class _TokenBucket:
    def __init__(self, rate: float = _MAX_RPM, window: float = 60.0) -> None:
        self._rate = rate
        self._window = window
        self._tokens = float(rate)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(float(self._rate), self._tokens + elapsed * (self._rate / self._window))
            self._last_refill = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) * (self._window / self._rate)
                await asyncio.sleep(wait)
                self._tokens = 0.0
                self._last_refill = time.monotonic()
            else:
                self._tokens -= 1.0


class GroqClient(LLMClient):
    name = "groq"
    supports_json = True
    _bucket = _TokenBucket()

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None

    def _ensure(self) -> Any:
        if self._client is None:
            from groq import AsyncGroq  # type: ignore[import-not-found]

            self._client = AsyncGroq(api_key=self.settings.groq_api_key)
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        await self._bucket.acquire()
        start = time.perf_counter()
        client = self._ensure()
        payload_messages = [m.model_dump() for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.settings.groq_model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await client.chat.completions.create(**kwargs)
        text = (resp.choices[0].message.content or "").strip()
        json_data = None
        if json_mode:
            try:
                json_data = json.loads(text)
            except json.JSONDecodeError:
                json_data = None
        elapsed = int((time.perf_counter() - start) * 1000)
        usage = resp.usage
        return LLMResponse(
            text=text,
            json_data=json_data,
            model=self.settings.groq_model,
            provider=self.name,
            latency_ms=elapsed,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            finish_reason=resp.choices[0].finish_reason or "stop",
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Groq does not provide embeddings.")

    async def health(self) -> bool:
        try:
            await self.complete(
                [LLMMessage(role="user", content="ping")],
                temperature=0,
                max_tokens=4,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Groq health failed: %s", e)
            return False
