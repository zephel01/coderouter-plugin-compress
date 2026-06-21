import json

from coderouter_plugin_compress.crushers.json_crush import crush_json


def test_array_of_dicts_becomes_columnar_and_smaller():
    rows = [{"id": i, "name": f"user{i}", "status": "ok" if i % 2 else "fail"} for i in range(50)]
    pretty = json.dumps(rows, indent=2)
    res = crush_json(pretty)
    assert res.changed
    assert len(res.text) < len(pretty)
    assert res.text.startswith("[json-table rows=50")
    # Semantics preserved: every value still present.
    for i in range(50):
        assert f"user{i}" in res.text
    assert "fail" in res.text and "ok" in res.text


def test_extra_keys_not_dropped():
    rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c", "x": 9}]
    res = crush_json(json.dumps(rows, indent=2))
    assert res.changed
    assert '"x":9' in res.text  # the odd-one-out key survives


def test_minify_path_for_nested_object():
    obj = {"a": {"b": {"c": [1, 2, 3]}}, "long": "x" * 200}
    pretty = json.dumps(obj, indent=4)
    res = crush_json(pretty)
    assert res.changed
    # Round-trips to the same data.
    assert json.loads(res.text) == obj


def test_invalid_json_passed_through():
    text = "this is not json at all { broken"
    res = crush_json(text)
    assert not res.changed
    assert res.text == text


def test_small_non_shrinkable_json_unchanged():
    res = crush_json('[1,2,3]')
    assert not res.changed


def test_delimiter_in_value_is_escaped():
    rows = [{"k": "a|b"}, {"k": "c|d"}, {"k": "e|f"}]
    res = crush_json(json.dumps(rows))
    assert res.changed
    # Pipe inside a value must be escaped so it can't be confused with the
    # column separator.
    assert "\\|" in res.text
