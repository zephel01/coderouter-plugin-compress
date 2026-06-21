from coderouter_plugin_compress.config import DEFAULT_PRESERVE_MARKERS
from coderouter_plugin_compress.crushers.log_crush import crush_log


def test_exact_duplicates_folded():
    text = "\n".join(["connecting to db"] * 20 + ["done", "x", "y", "z"])
    res = crush_log(text, DEFAULT_PRESERVE_MARKERS)
    assert res.changed
    assert "(x 20)" in res.text
    assert len(res.text) < len(text)


def test_template_run_folded():
    lines = [f"2026-06-21 10:00:{i:02d} INFO heartbeat seq={i}" for i in range(30)]
    text = "\n".join(lines)
    res = crush_log(text, DEFAULT_PRESERVE_MARKERS)
    assert res.changed
    assert "varying" in res.text


def test_error_line_preserved_verbatim():
    lines = ["INFO ok"] * 10
    lines.insert(5, "ERROR something exploded at module.py:42")
    lines += ["INFO ok"] * 10
    text = "\n".join(lines)
    res = crush_log(text, DEFAULT_PRESERVE_MARKERS)
    assert res.changed
    # The exact error line must survive unmodified.
    assert "ERROR something exploded at module.py:42" in res.text


def test_traceback_marker_preserved():
    body = ["DEBUG step"] * 8
    tb = ["Traceback (most recent call last):", '  File "x.py", line 1, in <module>']
    text = "\n".join(body + tb + body)
    res = crush_log(text, DEFAULT_PRESERVE_MARKERS)
    assert "Traceback (most recent call last):" in res.text


def test_short_input_unchanged():
    res = crush_log("a\nb\nc", DEFAULT_PRESERVE_MARKERS)
    assert not res.changed
