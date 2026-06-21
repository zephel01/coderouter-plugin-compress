import asyncio
import json

import pytest

from coderouter_plugin_compress.filter import CompressInputFilter, _extract_text
from coderouter_plugin_compress.stats import STATS
from conftest import FakeMessage, FakeRequest, tool_result_msg


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_stats():
    STATS.requests_seen = 0
    STATS.blocks_compressed = 0
    STATS.blocks_restored = 0
    STATS.original_tokens = 0
    STATS.compressed_tokens = 0
    STATS.crusher_counts.clear()
    yield


def _big_json_text():
    rows = [{"id": i, "name": f"user{i}", "status": "ok"} for i in range(100)]
    return json.dumps(rows, indent=2)


def test_tool_result_compressed_and_input_unchanged():
    original = _big_json_text()
    req = FakeRequest(messages=[tool_result_msg(original)])
    flt = CompressInputFilter(mode="safe", min_block_tokens=10)

    out = run(flt.transform(req))

    # New request object returned; original request not mutated.
    assert out is not req
    assert req.messages[0].content[0]["content"] == original

    new_text = out.messages[0].content[0]["content"]
    assert len(new_text) < len(original)
    assert "json-table" in new_text
    assert "coderouter-compress" in new_text  # CCR marker present
    assert STATS.blocks_compressed == 1


def test_mode_off_is_passthrough():
    req = FakeRequest(messages=[tool_result_msg(_big_json_text())])
    flt = CompressInputFilter(mode="off")
    out = run(flt.transform(req))
    assert out is req


def test_small_block_untouched():
    req = FakeRequest(messages=[tool_result_msg('{"a":1}')])
    flt = CompressInputFilter(mode="safe", min_block_tokens=200)
    out = run(flt.transform(req))
    assert out is req  # nothing changed → same object
    assert STATS.blocks_compressed == 0


def test_non_tool_result_blocks_left_alone():
    msg = FakeMessage(role="user", content=[{"type": "text", "text": "hi " * 500}])
    req = FakeRequest(messages=[msg])
    flt = CompressInputFilter(mode="safe", min_block_tokens=10)
    out = run(flt.transform(req))
    assert out is req  # text block isn't a target


def test_string_content_message_untouched():
    msg = FakeMessage(role="user", content="just a plain string")
    req = FakeRequest(messages=[msg])
    flt = CompressInputFilter(mode="safe")
    out = run(flt.transform(req))
    assert out is req


def test_crusher_exception_degrades_to_passthrough(monkeypatch):
    req = FakeRequest(messages=[tool_result_msg(_big_json_text())])
    flt = CompressInputFilter(mode="safe", min_block_tokens=10)

    import coderouter_plugin_compress.filter as fmod

    def boom(*a, **k):
        raise RuntimeError("crusher blew up")

    monkeypatch.setattr(fmod, "route_and_crush", boom)
    out = run(flt.transform(req))
    # Block left intact; engine not disrupted.
    assert out.messages[0].content[0]["content"] == req.messages[0].content[0]["content"]


def test_ccr_disabled_no_marker():
    req = FakeRequest(messages=[tool_result_msg(_big_json_text())])
    flt = CompressInputFilter(mode="safe", min_block_tokens=10, ccr=False)
    out = run(flt.transform(req))
    new_text = out.messages[0].content[0]["content"]
    assert "coderouter-compress" not in new_text
    assert "json-table" in new_text


def test_extract_text_variants():
    assert _extract_text("hello") == "hello"
    assert _extract_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"
    assert _extract_text([{"type": "image"}]) is None
    assert _extract_text(None) is None
