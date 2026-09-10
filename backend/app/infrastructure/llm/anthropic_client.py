"""Anthropic Claude adapter.

Added because Billeasy's brief names Claude as the preferred model. It is a plain
implementation of the existing `LLMClient` port — the router, the token-bucket
pattern, the retry/fallback ladder and every calling node are untouched. That was
the point of the exercise: if the port abstraction is real, a new provider is one
file, and if it isn't, this would have been a rewrite.

Three things differ from the OpenAI-shaped providers and are handled here:

1. The system prompt is a top-level ``system`` parameter, not a message role.
2. Sampling parameters (``temperature``/``top_p``/``top_k``) are **rejected with a
   400** on current models such as Claude Opus 5 and Sonnet 5. The router hands us a
   temperature anyway, so it is only forwarded to models that still accept it.
3. There is no ``response_format={"type": "json_object"}``. JSON mode is enforced by
   instruction plus a tolerant extractor, so a fenced or prose-wrapped object still
   parses instead of collapsing the whole plan.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from app.observability import get_logger
from app.settings import get_settings

from .base import LLMClient, LLMMessage, LLMResponse

logger = get_logger(__name__)

# Conservative default so a low-tier key does not trip 429s under the parallel
# message-generation fanout.
_MAX_RPM = 30

# Models that still accept sampling parameters. Everything current (Opus 5, Sonnet 5,
# Opus 4.7/4.8, Fable 5.x) returns a 400 if `temperature` is sent.
_TEMPERATURE_OK = ("claude-haiku-4-5", "claude-opus-4-6", "claude-sonnet-4-6")

_JSON_INSTRUCTION = (
    "Respond with a single valid JSON object and nothing else. "
    "No prose, no explanation, no markdown code fences."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


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


def _extract_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object out of a model response without being brittle about it."""
    if not text:
        return None
    for candidate in (text, *(m.group(1) for m in _FENCE_RE.finditer(text))):
        try:
            parsed = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    # Last resort: the outermost {...} span.
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


class AnthropicClient(LLMClient):
    name = "anthropic"
    supports_json = True
    _bucket = _TokenBucket()

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None

    def _ensure(self) -> Any:
        if self._client is None:
            from anthropic import AsyncAnthropic  # type: ignore[import-not-found]

            self._client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
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
        model = self.settings.anthropic_model

        # Claude takes the system prompt out of band.
        system_parts = [m.content for m in messages if m.role == "system"]
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        if not turns:
            turns = [{"role": "user", "content": " ".join(system_parts) or "Continue."}]
        if json_mode:
            system_parts.append(_JSON_INSTRUCTION)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": turns,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.settings.anthropic_effort},
        }
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)
        if model.startswith(_TEMPERATURE_OK):
            kwargs["temperature"] = temperature

        resp = await client.messages.create(**kwargs)

        # A safety decline returns HTTP 200 with stop_reason="refusal" — surface it as
        # an empty completion so the router falls through to the next provider rather
        # than handing a node an empty plan it will misread as a parse failure.
        if getattr(resp, "stop_reason", None) == "refusal":
            detail = getattr(getattr(resp, "stop_details", None), "category", None)
            logger.warning("Anthropic refused the request (category=%s)", detail)
            raise RuntimeError(f"anthropic refusal: {detail}")

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()

        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            json_data=_extract_json(text) if json_mode else None,
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            tokens_in=getattr(usage, "input_tokens", 0) or 0,
            tokens_out=getattr(usage, "output_tokens", 0) or 0,
            finish_reason=getattr(resp, "stop_reason", "stop") or "stop",
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Anthropic does not provide an embeddings endpoint.")

    async def health(self) -> bool:
        try:
            await self.complete(
                [LLMMessage(role="user", content="ping")],
                temperature=0,
                max_tokens=16,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Anthropic health failed: %s", e)
            return False
