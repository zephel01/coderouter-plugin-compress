"""Phase 3 — CacheAligner InputFilter tests."""
from dataclasses import dataclass, field, replace
from typing import Any

from coderouter_plugin_compress.cache_aligner import CacheAlignConfig, CacheAlignInputFilter
from test_filter import run


@dataclass
class FakeReq:
    """Mirrors the AnthropicRequest surface the filter touches."""
    system: Any = None
    tools: Any = None
    messages: list = field(default_factory=list)

    def model_copy(self, update: dict | None = None) -> "FakeReq":
        return replace(self, **(update or {}))


def _tool(name: str) -> dict:
    return {"name": name, "description": f"{name} tool", "input_schema": {"type": "object"}}


def test_cache_control_on_string_system():
    req = FakeReq(system="big system prompt " * 100)
    out = run(CacheAlignInputFilter().transform(req))
    assert isinstance(out.system, list)
    assert out.system[0]["cache_control"] == {"type": "ephemeral"}
    assert out.system[0]["text"].startswith("big system prompt")
    assert req.system == "big system prompt " * 100  # original untouched


def test_cache_control_on_list_system_last_block():
    req = FakeReq(system=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
    out = run(CacheAlignInputFilter().transform(req))
    assert "cache_control" not in out.system[0]
    assert out.system[1]["cache_control"] == {"type": "ephemeral"}


def test_cache_control_on_tools_last():
    req = FakeReq(tools=[_tool("a"), _tool("b"), _tool("c")])
    out = run(CacheAlignInputFilter().transform(req))
    assert "cache_control" not in out.tools[0]
    assert out.tools[-1]["cache_control"] == {"type": "ephemeral"}


def test_breakpoint_budget_clamped_to_4():
    cfg = CacheAlignConfig.from_kwargs(max_breakpoints=99)
    assert cfg.max_breakpoints == 4
    cfg2 = CacheAlignConfig.from_kwargs(max_breakpoints=0)
    assert cfg2.max_breakpoints == 1


def test_total_breakpoints_within_limit():
    req = FakeReq(system="sys " * 50, tools=[_tool("a"), _tool("b")])
    out = run(CacheAlignInputFilter(max_breakpoints=4).transform(req))
    n = _count_breakpoints(out)
    assert 1 <= n <= 4
    # Both tools-tail and system get one each here.
    assert n == 2


def test_budget_one_only_tools():
    req = FakeReq(system="sys " * 50, tools=[_tool("a")])
    out = run(CacheAlignInputFilter(max_breakpoints=1).transform(req))
    # Only one breakpoint allowed → goes to tools (processed first), not system.
    assert out.tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert isinstance(out.system, str)  # system left as-is (no budget)


def test_stabilize_tools_order():
    req = FakeReq(tools=[_tool("zebra"), _tool("alpha"), _tool("mike")])
    out = run(CacheAlignInputFilter(stabilize_tools_order=True).transform(req))
    names = [t["name"] for t in out.tools]
    assert names == ["alpha", "mike", "zebra"]


def test_inject_disabled_is_passthrough():
    req = FakeReq(system="sys " * 50, tools=[_tool("a")])
    out = run(CacheAlignInputFilter(inject_cache_control=False).transform(req))
    assert out is req  # nothing to do → same object


def test_no_system_no_tools_passthrough():
    req = FakeReq()
    out = run(CacheAlignInputFilter().transform(req))
    assert out is req


def test_transform_never_raises_on_bad_request():
    class Boom:
        system = "x" * 100

        @property
        def tools(self):
            raise RuntimeError("boom")

    out = run(CacheAlignInputFilter().transform(Boom()))
    assert isinstance(out, Boom)  # degraded to passthrough


def _count_breakpoints(req) -> int:
    n = 0
    if isinstance(req.system, list):
        n += sum(1 for b in req.system if isinstance(b, dict) and "cache_control" in b)
    if isinstance(req.tools, list):
        n += sum(1 for t in req.tools if isinstance(t, dict) and "cache_control" in t)
    return n
