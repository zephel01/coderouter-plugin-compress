"""End-to-end integration test against CodeRouter's REAL machinery.

Exercises the actual integration seams (no mocks of CodeRouter):
  1. CodeRouter's real plugin loader discovers our entry points.
  2. The real PluginsConfig allowlist gates activation (opt-in).
  3. The real PluginRegistry exposes our filter/observer.
  4. A real AnthropicRequest (pydantic) round-trips through the filter
     using the engine's own sequential-chain + model_copy semantics.

CodeRouter source is imported read-only; nothing in the repo is modified.
Run: python scripts/integration_test.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

# Real CodeRouter modules (read-only import via PYTHONPATH).
# NOTE: importing coderouter.adapters first establishes the canonical module
# init order; importing translation.anthropic in isolation trips a pre-existing
# circular import in CodeRouter (convert <-> adapters). We don't touch the repo.
import coderouter.adapters  # noqa: F401  (import-order side effect)
from coderouter.config.schemas import PluginsConfig
from coderouter.plugins.loader import discover_and_load
from coderouter.translation.anthropic import AnthropicRequest


def _make_request() -> AnthropicRequest:
    rows = [
        {"path": f"src/m{i}/handler.py", "line": 100 + i, "match": "def handle(self, r):"}
        for i in range(80)
    ]
    big_json = json.dumps(rows, indent=2)

    log_lines = [
        f"2026-06-21 10:{i // 60:02d}:{i % 60:02d} INFO heartbeat seq={i} latency={i % 30}ms"
        for i in range(300)
    ]
    log_lines.insert(150, "2026-06-21 10:02:30 FATAL disk full on /var; shutting down")
    big_log = "\n".join(log_lines)

    return AnthropicRequest(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": "search results below"},
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_json", "content": big_json},
                    {"type": "tool_result", "tool_use_id": "tu_log", "content": big_log},
                ],
            },
        ],
    )


async def _run_filter_chain(filters, request):
    """Reproduce the engine's InputFilter chaining: sequential, each filter
    sees the previous output; a raising filter is skipped (degraded continue)."""
    current = request
    for flt in filters:
        try:
            current = await flt.transform(current)
        except Exception as exc:  # mirror engine's input-filter-failed handling
            print(f"  (filter {flt.name} raised, kept pre-mutation request: {exc})")
    return current


def main() -> int:
    # 1. Real loader + real allowlist. Build the plugins block exactly as it
    #    would be parsed from providers.yaml.
    plugins_cfg = PluginsConfig(
        enabled=["compress", "compress-stats"],
        config={"compress": {"mode": "safe", "min_block_tokens": 10}},
    )
    config = SimpleNamespace(plugins=plugins_cfg)

    registry = discover_and_load(config)
    filters = registry.input_filters
    observers = registry.observers

    assert any(f.name == "compress" for f in filters), "compress filter not discovered/loaded"
    assert any(o.name == "compress-stats" for o in observers), "observer not discovered/loaded"
    print(f"[1] loader: input_filters={[f.name for f in filters]} observers={[o.name for o in observers]}")

    # 2. Opt-in gate: a config WITHOUT compress must yield no input filters.
    empty_reg = discover_and_load(SimpleNamespace(plugins=PluginsConfig(enabled=[])))
    assert not empty_reg.input_filters, "plugin activated without opt-in!"
    print("[2] opt-in gate: empty enabled -> no filters (supply-chain defense holds)")

    # 3. Real request through the real chain.
    req = _make_request()
    before_json = req.messages[1].content[0]["content"]
    before_log = req.messages[1].content[1]["content"]

    out = asyncio.run(_run_filter_chain(filters, req))

    after_json = out.messages[1].content[0]["content"]
    after_log = out.messages[1].content[1]["content"]

    # Original request object untouched (immutability contract).
    assert req.messages[1].content[0]["content"] == before_json
    assert out is not req

    # Both blocks compressed.
    assert len(after_json) < len(before_json), "json block not compressed"
    assert len(after_log) < len(before_log), "log block not compressed"
    # Marker preserved verbatim.
    assert "FATAL disk full on /var; shutting down" in after_log, "FATAL line lost!"
    # Plain-string message left alone.
    assert out.messages[0].content == "search results below"

    print(f"[3] json block: {len(before_json):>6} -> {len(after_json):>6} chars")
    print(f"    log  block: {len(before_log):>6} -> {len(after_log):>6} chars  (FATAL intact)")

    # 4. Observer fires without raising (fire-and-forget contract).
    asyncio.run(observers[0].on_event("request_completed", {"provider": "test", "latency_ms": 12}))
    asyncio.run(observers[0].on_event("unknown_event", {}))  # must be tolerated
    print("[4] observer: request_completed + unknown_event handled, no raise")

    # 5. The compressed request still serializes as a valid Anthropic body.
    body = out.model_dump(exclude_none=True)
    assert body["messages"][1]["content"][0]["type"] == "tool_result"
    print("[5] post-compress request re-serializes to a valid Anthropic body")

    # 6. Phase 2 — CCR re-expansion across two turns, real request objects.
    _phase2_reexpand(filters)

    # 7. Phase 3 — CacheAligner via the real loader on a real request.
    _phase3_cache_align()

    print("\nINTEGRATION OK — all assertions passed against real CodeRouter machinery.")
    return 0


def _phase3_cache_align():
    """Load cache-align via the real loader, run it on a real AnthropicRequest,
    and confirm the cache_control markers survive model_dump (what the native
    Anthropic adapter sends upstream)."""
    reg = discover_and_load(
        SimpleNamespace(plugins=PluginsConfig(
            enabled=["cache-align"],
            config={"cache-align": {"max_breakpoints": 4}},
        ))
    )
    flt = next(f for f in reg.input_filters if f.name == "cache-align")

    req = AnthropicRequest(
        model="claude-sonnet-4-6", max_tokens=256,
        system="You are Claude Code. " * 200,  # big, stable system prompt
        tools=[
            {"name": "read", "description": "read a file", "input_schema": {"type": "object"}},
            {"name": "grep", "description": "search", "input_schema": {"type": "object"}},
        ],
        messages=[{"role": "user", "content": "hi"}],
    )
    out = asyncio.run(flt.transform(req))

    body = out.model_dump(exclude_none=True)  # exactly what the native adapter dumps
    sys_blocks = body["system"]
    assert isinstance(sys_blocks, list) and sys_blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert body["tools"][-1]["cache_control"] == {"type": "ephemeral"}

    n_bp = sum(1 for b in sys_blocks if isinstance(b, dict) and "cache_control" in b)
    n_bp += sum(1 for t in body["tools"] if isinstance(t, dict) and "cache_control" in t)
    assert 1 <= n_bp <= 4, f"breakpoints out of range: {n_bp}"
    # Original request unchanged.
    assert isinstance(req.system, str)
    print(f"[7] cache-align: model_dump carries {n_bp} cache_control breakpoints "
          f"(system tail + tools tail); original request untouched")


def _phase2_reexpand(filters):
    """Turn 1 compresses a block and advertises its ccr id; turn 2 the model
    echoes the id and the block is restored to the original."""
    from coderouter_plugin_compress.ccr import CCRStore

    rows = [{"id": i, "v": f"value-{i}", "ok": True} for i in range(90)]
    original = json.dumps(rows, indent=2)
    cid = CCRStore.key_for(original)

    # Turn 1: just the tool_result.
    t1 = AnthropicRequest(
        model="m", max_tokens=512,
        messages=[{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu", "content": original}]}],
    )
    out1 = asyncio.run(_run_filter_chain(filters, t1))
    sent1 = out1.messages[0].content[0]["content"]
    assert len(sent1) < len(original) and f"expand {cid}" in sent1, "turn1 should compress + advertise id"

    # Turn 2: client resends the ORIGINAL tool_result + the model's expand request.
    t2 = AnthropicRequest(
        model="m", max_tokens=512,
        messages=[
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu", "content": original}]},
            {"role": "assistant", "content": f"need details — expand {cid}"},
        ],
    )
    out2 = asyncio.run(_run_filter_chain(filters, t2))
    sent2 = out2.messages[0].content[0]["content"]
    assert sent2 == original, "turn2 referenced block must be restored to original"
    print(f"[6] CCR re-expand: turn1 {len(original)}->{len(sent1)} chars (id {cid}); "
          f"turn2 restored to {len(sent2)} chars (==original)")


if __name__ == "__main__":
    sys.exit(main())
