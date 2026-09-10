"""Gemini 2.0 Flash adapter. Strict-JSON friendly."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.observability import get_logger
from app.settings import get_settings

from .base import LLMClient, LLMMessage, LLMResponse

logger = get_logger(__name__)

# Free-tier limit is ~60 RPM; stay under it.
_MAX_RPM_GEMINI = 36


class _TokenBucket:
    def __init__(self, rate: float, window: float = 60.0) -> None:
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


class GeminiClient(LLMClient):
    name = "gemini"
    supports_json = True
    _bucket = _TokenBucket(rate=_MAX_RPM_GEMINI)

    def __init__(self) -> None:
        self.settings = get_settings()
        self._configured = False

    def _ensure(self) -> Any:
        import google.generativeai as genai  # type: ignore[import-not-found]

        if not self._configured:
            genai.configure(api_key=self.settings.gemini_api_key)
            self._configured = True
        return genai

    @staticmethod
    def _to_gemini_messages(messages: list[LLMMessage]) -> tuple[str, list[dict[str, Any]]]:
        system_chunks: list[str] = []
        history: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_chunks.append(m.content)
            else:
                history.append({"role": "user" if m.role == "user" else "model", "parts": [m.content]})
        return "\n\n".join(system_chunks), history

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
        genai = self._ensure()
        sys, history = self._to_gemini_messages(messages)

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        model = genai.GenerativeModel(
            self.settings.gemini_model,
            system_instruction=sys or None,
            generation_config=generation_config,
        )

        # google-generativeai is sync; we run in a worker thread to keep loop free
        import asyncio

        def _run() -> Any:
            return model.generate_content(history)

        resp = await asyncio.to_thread(_run)
        text = (resp.text or "").strip()
        json_data: dict[str, Any] | None = None
        if json_mode and text:
            try:
                json_data = json.loads(text)
            except json.JSONDecodeError:
                # try to salvage: take the first {...} block
                stripped = _extract_json_block(text)
                if stripped:
                    try:
                        json_data = json.loads(stripped)
                    except json.JSONDecodeError:
                        json_data = None
        elapsed = int((time.perf_counter() - start) * 1000)
        usage = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text=text,
            json_data=json_data,
            model=self.settings.gemini_model,
            provider=self.name,
            latency_ms=elapsed,
            tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        genai = self._ensure()
        import asyncio

        def _run_one(t: str) -> list[float]:
            r = genai.embed_content(model=self.settings.gemini_embed_model, content=t)
            return list(r["embedding"])

        return await asyncio.gather(*(asyncio.to_thread(_run_one, t) for t in texts))

    async def health(self) -> bool:
        try:
            await self.complete(
                [LLMMessage(role="user", content="ping")],
                temperature=0,
                max_tokens=4,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Gemini health failed: %s", e)
            return False


def _extract_json_block(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None
