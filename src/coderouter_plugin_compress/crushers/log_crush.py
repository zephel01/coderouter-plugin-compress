"""Log / stack-trace compressor (pure stdlib).

Logs are the highest-yield target (headroom's SRE workload: 92%). They are
dominated by repetition: identical lines repeated, and near-identical lines
that differ only in a timestamp, counter, hex address, or UUID.

Strategy, all lossless for the *signal*:

1. **Marker preservation** — any line containing a preserve marker
   (FATAL/ERROR/Traceback/...) is emitted verbatim and never folded. This
   is the safety guarantee: the line that matters survives intact.
2. **Exact-run folding** — N consecutive identical lines become one line
   plus ``(x N)``.
3. **Template folding** — consecutive lines that are identical after
   masking volatile tokens (timestamps, numbers, hex, UUIDs) collapse into
   one representative line plus ``(x N, varying)``.

Non-consecutive duplicates are left alone to preserve ordering/structure.
"""
from __future__ import annotations

import re

from coderouter_plugin_compress.crushers.base import CrushResult

# Heuristic gate: only treat input as a log if it has several lines.
_MIN_LINES = 6

_TS_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
    re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"),
]
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
# Mask any digit run, including ones glued to letters (e.g. "12ms", "seq=3"),
# so structurally-identical log lines collapse to one template.
_NUM = re.compile(r"\d+")


def _template(line: str) -> str:
    """Mask volatile tokens so structurally-identical lines compare equal."""
    s = line
    for p in _TS_PATTERNS:
        s = p.sub("§TS§", s)
    s = _UUID.sub("§UUID§", s)
    s = _HEX.sub("§HEX§", s)
    s = _NUM.sub("§N§", s)
    return s


def crush_log(text: str, preserve_markers: tuple[str, ...] = ()) -> CrushResult:
    lines = text.split("\n")
    if len(lines) < _MIN_LINES:
        return CrushResult.unchanged(text, "log")

    markers_lower = tuple(m.lower() for m in preserve_markers)

    def is_marker(line: str) -> bool:
        low = line.lower()
        return any(m in low for m in markers_lower)

    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # Preserve marker lines verbatim, no folding across them.
        if is_marker(line):
            out.append(line)
            i += 1
            continue

        # Count an exact-run first.
        j = i + 1
        while j < n and lines[j] == line and not is_marker(lines[j]):
            j += 1
        exact = j - i
        if exact >= 2:
            out.append(f"{line}  (x {exact})")
            i = j
            continue

        # No exact run: try a template-run of >=3 lines.
        tmpl = _template(line)
        k = i + 1
        while k < n and not is_marker(lines[k]) and _template(lines[k]) == tmpl:
            k += 1
        tmpl_run = k - i
        if tmpl_run >= 3:
            out.append(f"{line}  (x {tmpl_run}, varying)")
            i = k
            continue

        out.append(line)
        i += 1

    compressed = "\n".join(out)
    if len(compressed) < len(text):
        return CrushResult(text=compressed, changed=True, crusher="log")
    return CrushResult.unchanged(text, "log")
