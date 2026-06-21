"""JSON compressor (SmartCrusher-equivalent, pure stdlib).

Two wins, both semantics-preserving:

1. **Whitespace** — pretty-printed JSON (2/4-space indent, newlines) is
   re-serialized minified. This alone reclaims a large fraction of tokens
   in tool outputs that pretty-print by default (most do).
2. **Array-of-objects key dedup** — a list of records repeats every key on
   every row. We detect a homogeneous (or near-homogeneous) array of dicts
   and emit a compact columnar table: the key set once in a header, then
   one pipe-delimited line per row. For 100 records with 3 keys that turns
   ~300 key repetitions into 3.

The original is always retained by CCR upstream, so this is a display
transform, not a destructive edit. We keep it deterministic (sorted keys)
which also helps prefix-cache stability downstream.
"""
from __future__ import annotations

import json
from typing import Any

from coderouter_plugin_compress.crushers.base import CrushResult

# Need at least this many rows before columnar encoding is worth the
# header overhead and the loss of explicit per-field labels.
_MIN_ROWS_FOR_TABLE = 3
# Fraction of rows that must share the dominant key set to treat the array
# as a table. Below this we fall back to plain minification.
_HOMOGENEITY = 0.7


def crush_json(text: str) -> CrushResult:
    """Compress a JSON string. Returns unchanged on any parse failure."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return CrushResult.unchanged(text, "json")
    try:
        data = json.loads(stripped)
    except (ValueError, RecursionError):
        return CrushResult.unchanged(text, "json")

    if isinstance(data, list):
        table = _try_columnar(data)
        if table is not None and len(table) < len(text):
            return CrushResult(text=table, changed=True, crusher="json")

    # Fallback: minify (drop insignificant whitespace).
    try:
        minified = json.dumps(data, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return CrushResult.unchanged(text, "json")

    if len(minified) < len(text):
        return CrushResult(text=minified, changed=True, crusher="json")
    return CrushResult.unchanged(text, "json")


def _try_columnar(rows: list[Any]) -> str | None:
    """Render a homogeneous array of dicts as a compact table, or None."""
    if len(rows) < _MIN_ROWS_FOR_TABLE:
        return None
    if not all(isinstance(r, dict) for r in rows):
        return None

    # Determine the dominant key set.
    from collections import Counter

    key_sig: Counter[tuple[str, ...]] = Counter()
    for r in rows:
        key_sig[tuple(sorted(r.keys()))] += 1
    dominant_keys, dominant_count = key_sig.most_common(1)[0]
    if not dominant_keys:
        return None
    if dominant_count / len(rows) < _HOMOGENEITY:
        return None

    cols = list(dominant_keys)
    lines = [f"[json-table rows={len(rows)} cols={','.join(cols)}]"]
    for r in rows:
        cells = []
        for c in cols:
            cells.append(_scalar(r.get(c)))
        # Rows that don't match the dominant schema get their extra keys
        # appended so no information is silently dropped.
        extra = {k: v for k, v in r.items() if k not in dominant_keys}
        line = "|".join(cells)
        if extra:
            line += "|+" + json.dumps(extra, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
        lines.append(line)
    return "\n".join(lines)


def _scalar(value: Any) -> str:
    """Render a cell. Nested structures are minified-JSON inline."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        s = str(value)
        # Escape the delimiter and newlines so rows stay parseable.
        return s.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "\\n")
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, sort_keys=True).replace(
        "|", "\\|"
    )
