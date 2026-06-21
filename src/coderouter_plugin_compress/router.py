"""ContentRouter: detect content type, dispatch to the right crusher.

Mirrors headroom's ContentRouter. Detection order is cheapest-first and
conservative: when in doubt, fall through to text (which itself no-ops on
small input), so the worst case is "passed through unchanged".
"""
from __future__ import annotations

import re

from coderouter_plugin_compress.config import CompressConfig
from coderouter_plugin_compress.crushers import CrushResult, crush_json, crush_log, crush_text

# Signals that a blob is log-shaped: many lines, several carrying a
# timestamp or a log level.
_LOGLEVEL = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b")
_TS = re.compile(r"\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}")


def _looks_like_log(text: str) -> bool:
    lines = text.split("\n", 60)
    if len(lines) < 6:
        return False
    sample = lines[:60]
    hits = sum(1 for ln in sample if _LOGLEVEL.search(ln) or _TS.search(ln))
    return hits >= max(3, len(sample) // 5)


def _looks_like_json(text: str) -> bool:
    s = text.strip()
    return bool(s) and s[0] in "[{" and s[-1] in "]}"


def route_and_crush(text: str, cfg: CompressConfig) -> CrushResult:
    """Pick a crusher by content type and run it. Always returns a result."""
    enabled = cfg.crushers

    if "json" in enabled and _looks_like_json(text):
        res = crush_json(text)
        if res.changed:
            return res
        # JSON that didn't shrink: don't fall through to log/text — it's
        # structured data, leave it as-is.
        return res

    if "log" in enabled and _looks_like_log(text):
        res = crush_log(text, cfg.preserve_markers)
        if res.changed:
            return res

    if "text" in enabled:
        return crush_text(text, cfg.preserve_markers)

    return CrushResult.unchanged(text)
