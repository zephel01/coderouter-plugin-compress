"""Phase 2 — CCR deterministic re-expansion tests."""
import json
import time

import pytest

from coderouter_plugin_compress.ccr import CCRStore, find_referenced_ids
from coderouter_plugin_compress.filter import CompressInputFilter
from coderouter_plugin_compress.stats import STATS
from conftest import FakeMessage, FakeRequest, tool_result_msg
from test_filter import run


@pytest.fixture(autouse=True)
def reset_stats():
    for attr in ("requests_seen", "blocks_compressed", "blocks_restored",
                 "original_tokens", "compressed_tokens"):
        setattr(STATS, attr, 0)
    STATS.crusher_counts.clear()
    yield


def _big_json_text(n=100):
    rows = [{"id": i, "name": f"user{i}", "status": "ok"} for i in range(n)]
    return json.dumps(rows, indent=2)


def test_id_is_content_hash_stable():
    t = _big_json_text()
    # Same content → same id across independent computations / turns.
    assert CCRStore.key_for(t) == CCRStore.key_for(t)
    assert find_referenced_ids(f"please expand {CCRStore.key_for(t)} now") == {CCRStore.key_for(t)}


def test_marker_advertises_expandable_id():
    req = FakeRequest(messages=[tool_result_msg(_big_json_text())])
    flt = CompressInputFilter(mode="safe", min_block_tokens=10)
    out = run(flt.transform(req))
    text = out.messages[0].content[0]["content"]
    cid = CCRStore.key_for(_big_json_text())
    assert f"expand {cid}" in text  # the model is told how to ask


def test_referenced_block_is_restored_uncompressed():
    original = _big_json_text()
    cid = CCRStore.key_for(original)
    # Turn N+1: client resends the original tool_result, plus an assistant
    # turn where the model asked to expand that id.
    req = FakeRequest(
        messages=[
            tool_result_msg(original),
            FakeMessage(role="assistant", content=f"I need the full data, expand {cid}"),
        ]
    )
    flt = CompressInputFilter(mode="aggressive", min_block_tokens=10)
    out = run(flt.transform(req))

    # The referenced block is passed through uncompressed.
    assert out.messages[0].content[0]["content"] == original
    assert STATS.blocks_restored == 1
    assert STATS.blocks_compressed == 0


def test_unreferenced_block_still_compressed():
    original = _big_json_text()
    req = FakeRequest(
        messages=[
            tool_result_msg(original),
            FakeMessage(role="assistant", content="thanks, that's enough"),
        ]
    )
    flt = CompressInputFilter(mode="aggressive", min_block_tokens=10)
    out = run(flt.transform(req))
    assert len(out.messages[0].content[0]["content"]) < len(original)
    assert STATS.blocks_restored == 0
    assert STATS.blocks_compressed == 1


def test_only_referenced_block_restored_others_compressed():
    a = _big_json_text(80)
    b = "\n".join(f"2026-06-21 10:00:{i:02d} INFO line seq={i}" for i in range(60))
    cid_a = CCRStore.key_for(a)
    msg = FakeMessage(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": "t1", "content": a},
            {"type": "tool_result", "tool_use_id": "t2", "content": b},
        ],
    )
    req = FakeRequest(
        messages=[msg, FakeMessage(role="assistant", content=f"expand {cid_a}")]
    )
    flt = CompressInputFilter(mode="aggressive", min_block_tokens=10)
    out = run(flt.transform(req))
    blocks = out.messages[0].content
    assert blocks[0]["content"] == a                      # restored
    assert len(blocks[1]["content"]) < len(b)             # still compressed
    assert STATS.blocks_restored == 1 and STATS.blocks_compressed == 1


def test_restore_off_ignores_reference():
    original = _big_json_text()
    cid = CCRStore.key_for(original)
    req = FakeRequest(
        messages=[
            tool_result_msg(original),
            FakeMessage(role="assistant", content=f"expand {cid}"),
        ]
    )
    flt = CompressInputFilter(mode="aggressive", min_block_tokens=10, ccr_restore="off")
    out = run(flt.transform(req))
    # With restore off, the block is compressed despite the reference.
    assert len(out.messages[0].content[0]["content"]) < len(original)
    assert STATS.blocks_restored == 0


def test_reference_detected_in_tool_use_input():
    original = _big_json_text()
    cid = CCRStore.key_for(original)
    msg = FakeMessage(
        role="assistant",
        content=[{"type": "tool_use", "name": "retrieve", "input": {"id": cid}}],
    )
    req = FakeRequest(messages=[tool_result_msg(original), msg])
    flt = CompressInputFilter(mode="aggressive", min_block_tokens=10)
    out = run(flt.transform(req))
    assert out.messages[0].content[0]["content"] == original
    assert STATS.blocks_restored == 1


def test_store_ttl_expiry():
    store = CCRStore(ttl_s=0.05)
    k = store.put("hello" * 100)
    assert store.get(k) is not None
    time.sleep(0.08)
    assert store.get(k) is None  # expired


def test_store_byte_cap_evicts():
    store = CCRStore(max_entries=100, max_bytes=300)
    k1 = store.put("a" * 200)
    store.put("b" * 200)  # total would exceed 300 → evicts k1
    assert store.get(k1) is None
