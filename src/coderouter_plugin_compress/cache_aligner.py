"""CacheAligner — prefix stabilization + Anthropic prompt-cache injection.

Phase 3. Implemented as a *separate InputFilter* (entry point ``cache-align``)
rather than a core edit, so CodeRouter itself is never modified. The filter
mutates the inbound AnthropicRequest; the native Anthropic adapter forwards
the added ``cache_control`` markers verbatim (it sends ``req.model_dump()`` to
api.anthropic.com). On OpenAI-compat / local routes the markers are dropped
harmlessly during Anthropic→OpenAI translation, so enabling this is safe on
every route.

Two independent, opt-in behaviors:

1. **cache_control injection** (default on when the filter is enabled) — adds
   an ``ephemeral`` breakpoint at the end of the stable prefix (tools and/or
   the system prompt). Claude Code resends a 15-20k-token system prompt every
   turn; caching it cuts paid-route prefill cost and latency dramatically.
   Anthropic allows at most 4 breakpoints — we clamp to that.

2. **tool-order stabilization** (default off — order changes are higher risk)
   — sorts tool definitions by name so the prefix is byte-identical across
   turns, which also helps server-side prefix caches on llama.cpp / Ollama.

Like every filter here, it treats the request as immutable and never raises
into the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_EPHEMERAL = {"type": "ephemeral"}


@dataclass(frozen=True)
class CacheAlignConfig:
    inject_cache_control: bool = True
    cache_system: bool = True
    cache_tools: bool = True
    stabilize_tools_order: bool = False
    max_breakpoints: int = 4

    @staticmethod
    def from_kwargs(**cfg: Any) -> "CacheAlignConfig":
        def _b(key: str, default: bool) -> bool:
            return bool(cfg.get(key, default))

        try:
            mbp = int(cfg.get("max_breakpoints", 4))
        except (TypeError, ValueError):
            mbp = 4
        mbp = max(1, min(4, mbp))  # Anthropic hard limit is 4
        return CacheAlignConfig(
            inject_cache_control=_b("inject_cache_control", True),
            cache_system=_b("cache_system", True),
            cache_tools=_b("cache_tools", True),
            stabilize_tools_order=_b("stabilize_tools_order", False),
            max_breakpoints=mbp,
        )


class CacheAlignInputFilter:
    """InputFilter that stabilizes the prompt prefix and marks cache breakpoints."""

    name = "cache-align"

    def __init__(self, **cfg: Any) -> None:
        self._cfg = CacheAlignConfig.from_kwargs(**cfg)

    async def transform(self, request: Any) -> Any:
        try:
            return self._apply(request)
        except Exception:
            # Never disrupt the engine; pass the request through untouched.
            return request

    def _apply(self, request: Any) -> Any:
        cfg = self._cfg
        budget = cfg.max_breakpoints
        update: dict[str, Any] = {}

        # --- tools: optional reorder, optional cache breakpoint --------------
        # Operate on the ORIGINAL tool objects (keeping their type), so the
        # native adapter's ``model_dump`` serializes them cleanly. Replacing
        # typed AnthropicTool models with bare dicts would trigger a pydantic
        # serialization warning on the hot path.
        tools = getattr(request, "tools", None)
        if isinstance(tools, list) and tools:
            new_tools = list(tools)
            changed = False
            if cfg.stabilize_tools_order:
                ordered = sorted(new_tools, key=lambda t: _tool_name(t))
                if [_tool_name(t) for t in ordered] != [_tool_name(t) for t in new_tools]:
                    new_tools = ordered
                    changed = True
            if cfg.inject_cache_control and cfg.cache_tools and budget > 0:
                new_tools[-1] = _with_cache_control(new_tools[-1])
                budget -= 1
                changed = True
            if changed:
                update["tools"] = new_tools

        # --- system: cache breakpoint on the (last) stable block -------------
        if cfg.inject_cache_control and cfg.cache_system and budget > 0:
            system = getattr(request, "system", None)
            if isinstance(system, list) and system:
                sys_blocks = list(system)
                last = dict(sys_blocks[-1]) if isinstance(sys_blocks[-1], dict) else {
                    "type": "text", "text": str(sys_blocks[-1])
                }
                last["cache_control"] = _EPHEMERAL
                sys_blocks[-1] = last
                update["system"] = sys_blocks
                budget -= 1
            elif isinstance(system, str) and system.strip():
                update["system"] = [
                    {"type": "text", "text": system, "cache_control": _EPHEMERAL}
                ]
                budget -= 1

        if not update:
            return request
        return request.model_copy(update=update)


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name", ""))
    return str(getattr(tool, "name", ""))


def _with_cache_control(tool: Any) -> Any:
    """Return a copy of ``tool`` carrying an ephemeral cache breakpoint,
    preserving its original type (pydantic model or dict)."""
    if isinstance(tool, dict):
        return {**tool, "cache_control": _EPHEMERAL}
    copy = getattr(tool, "model_copy", None)
    if callable(copy):
        # AnthropicTool has extra="allow", so cache_control round-trips cleanly.
        return copy(update={"cache_control": _EPHEMERAL})
    # Fallback: bare dict (still serializes, just loses the typed wrapper).
    dump = getattr(tool, "model_dump", None)
    base = dump(exclude_none=True) if callable(dump) else dict(tool)
    return {**base, "cache_control": _EPHEMERAL}
