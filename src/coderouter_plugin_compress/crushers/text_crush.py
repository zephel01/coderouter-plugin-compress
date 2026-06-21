"""Generic long-text compressor (conservative middle-elision).

Last resort for content that isn't JSON or log-shaped. We never paraphrase
(that needs an ML model — phase 4); we only elide the *middle* of very long
blocks while keeping the head and tail, which is where signal usually sits
(the command, and its result/error). Lines containing preserve markers are
kept even if they fall in the elided middle.
"""
from __future__ import annotations

from coderouter_plugin_compress.crushers.base import CrushResult

# Only act on genuinely large blocks; small text isn't worth eliding.
_MIN_CHARS = 4000
_HEAD_LINES = 40
_TAIL_LINES = 20


def crush_text(text: str, preserve_markers: tuple[str, ...] = ()) -> CrushResult:
    if len(text) < _MIN_CHARS:
        return CrushResult.unchanged(text, "text")

    lines = text.split("\n")
    if len(lines) <= _HEAD_LINES + _TAIL_LINES + 5:
        return CrushResult.unchanged(text, "text")

    markers_lower = tuple(m.lower() for m in preserve_markers)
    head = lines[:_HEAD_LINES]
    tail = lines[-_TAIL_LINES:]
    middle = lines[_HEAD_LINES:-_TAIL_LINES]

    kept_middle = [ln for ln in middle if any(m in ln.lower() for m in markers_lower)]
    elided = len(middle) - len(kept_middle)
    if elided <= 0:
        return CrushResult.unchanged(text, "text")

    marker_note = (
        f"\n[... {elided} lines elided; {len(kept_middle)} marker lines kept ...]\n"
    )
    parts = head + ([marker_note] if not kept_middle else [marker_note] + kept_middle) + tail
    compressed = "\n".join(parts)
    if len(compressed) < len(text):
        return CrushResult(text=compressed, changed=True, crusher="text")
    return CrushResult.unchanged(text, "text")
