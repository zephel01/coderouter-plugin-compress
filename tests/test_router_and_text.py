from coderouter_plugin_compress.config import CompressConfig
from coderouter_plugin_compress.crushers.text_crush import crush_text
from coderouter_plugin_compress.router import route_and_crush, _looks_like_json, _looks_like_log


def test_router_detects_json():
    import json
    rows = [{"id": i, "v": "ok"} for i in range(20)]
    res = route_and_crush(json.dumps(rows, indent=2), CompressConfig())
    assert res.crusher == "json" and res.changed


def test_router_detects_log():
    text = "\n".join(f"2026-06-21 10:00:{i:02d} INFO line {i}" for i in range(20))
    res = route_and_crush(text, CompressConfig())
    assert res.crusher == "log" and res.changed


def test_detectors():
    assert _looks_like_json('[1,2,3]')
    assert _looks_like_json('{"a":1}')
    assert not _looks_like_json("hello")
    assert _looks_like_log("\n".join(["10:00:01 INFO x"] * 8))
    assert not _looks_like_log("just\na\nfew\nlines")


def test_text_middle_elided_keeps_markers():
    head = ["line head"] * 40
    mid = ["filler"] * 500
    mid[250] = "ERROR deep in the middle"
    tail = ["line tail"] * 20
    text = "\n".join(head + mid + tail)
    res = crush_text(text, ("ERROR",))
    assert res.changed
    assert "ERROR deep in the middle" in res.text
    assert "lines elided" in res.text
    assert len(res.text) < len(text)
