"""LLM port — every provider implements this Protocol."""
from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    text: str
    json_data: dict[str, Any] | None = None
    model: str
    provider: str
    latency_ms: int = 0
    finish_reason: str = "stop"
    tokens_in: int = 0
    tokens_out: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    name: str
    supports_json: bool

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def health(self) -> bool: ...
