"""Single source of truth for tools.

Each tool:
  - Declares typed input/output via Pydantic models
  - Auto-exports its JSON schema for the LLM
  - Is registered via a decorator and discoverable through `/tools`
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.infrastructure.tool_cache import CACHEABLE_TOOLS, get_cached, make_cache_key, put_cached
from app.observability import get_logger
from app.settings import get_settings

logger = get_logger(__name__)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[..., Awaitable[BaseModel]]

    def json_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
        }


_REGISTRY: dict[str, ToolSpec] = {}


def tool(
    name: str,
    description: str,
    input_model: type[BaseModel],
    output_model: type[BaseModel],
):
    """Decorator. Registers an async function as a callable agent tool."""
    def _wrap(fn: Callable[..., Awaitable[BaseModel]]) -> Callable[..., Awaitable[BaseModel]]:
        if name in _REGISTRY:
            raise ValueError(f"Tool '{name}' already registered.")
        _REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            input_model=input_model,
            output_model=output_model,
            handler=fn,
        )
        return fn

    return _wrap


def get_registry() -> dict[str, ToolSpec]:
    if not _REGISTRY:
        # Trigger import side-effects
        from app.tools import bootstrap_tools  # noqa: F401, PLC0415

        bootstrap_tools()
    return _REGISTRY


async def invoke_tool(name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Validate args, run the tool with a timeout, return a structured envelope."""
    registry = get_registry()
    spec = registry.get(name)
    if spec is None:
        return {"ok": False, "error": f"tool_not_found:{name}", "data": None, "latency_ms": 0}

    started = time.perf_counter()
    try:
        args_model = spec.input_model.model_validate(raw_args or {})
    except ValidationError as ve:
        return {
            "ok": False,
            "error": f"invalid_args: {ve.errors()}",
            "data": None,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    settings = get_settings()

    # Cache the read-only, deterministic tools. The key is the *raw* args — the same
    # JSON two plans would produce — so an identical repeat call replays instead of
    # recomputing, within the configured TTL.
    cache_key: str | None = None
    if name in CACHEABLE_TOOLS and settings.tool_cache_ttl_seconds > 0:
        cache_key = make_cache_key(name, raw_args or {})
        cached_started = time.perf_counter()
        cached = await get_cached(cache_key, settings.tool_cache_ttl_seconds)
        if cached is not None:
            return {
                **cached,
                "cache": "hit",
                "latency_ms": int((time.perf_counter() - cached_started) * 1000),
            }

    try:
        result = await asyncio.wait_for(
            spec.handler(args_model),
            timeout=settings.agent_tool_timeout_seconds,
        )
        envelope = {
            "ok": True,
            "tool": name,
            "data": result.model_dump() if isinstance(result, BaseModel) else result,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
        if cache_key is not None:
            await put_cached(cache_key, envelope)
        return envelope
    except TimeoutError:
        return {
            "ok": False,
            "tool": name,
            "error": "timeout",
            "data": None,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("Tool %s raised", name)
        return {
            "ok": False,
            "tool": name,
            "error": f"{type(e).__name__}: {e}",
            "data": None,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
