"""Configuration schema for the compress plugin.

Kept dependency-free: a plain dataclass with explicit validation rather
than pydantic, so the plugin imposes no dependency beyond the standard
library. The CodeRouter loader passes ``plugins.config["compress"]`` as a
plain dict to ``CompressInputFilter(**cfg)``; we normalize it here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Lines matching these (case-insensitive substring) are NEVER dropped or
# folded by any crusher. Failure signal preservation is the whole point of
# "same answers, fewer tokens".
DEFAULT_PRESERVE_MARKERS: tuple[str, ...] = (
    "FATAL",
    "ERROR",
    "CRITICAL",
    "Traceback",
    "Exception",
    "panic:",
    "WARN",
)

VALID_MODES = ("off", "safe", "aggressive")
VALID_CRUSHERS = ("json", "log", "text")
VALID_TARGETS = ("tool_result",)
VALID_RESTORE = ("off", "explicit")


@dataclass(frozen=True)
class CompressConfig:
    """Validated compression settings.

    Attributes:
        mode: ``off`` (no-op), ``safe`` (lossless-ish, keeps short form),
            or ``aggressive`` (heavier elision; required for CCR re-expand).
        min_block_tokens: blocks estimated below this are passed through
            untouched (compression overhead not worth it for tiny blocks).
        targets: which Anthropic content-block types to compress.
        crushers: which compressors are enabled, in priority order.
        ccr: store originals locally so they can be referenced later.
        ccr_restore: ``explicit`` re-expands a block when a later turn echoes
            its ``ccr_<id>`` tag (deterministic, default); ``off`` disables
            re-expansion entirely.
        preserve_markers: substrings whose lines are always kept verbatim.
        metering_tokenizer_path: optional local tokenizer.json for accurate
            (CJK-correct) before/after token measurement.
    """

    mode: str = "safe"
    min_block_tokens: int = 200
    targets: tuple[str, ...] = ("tool_result",)
    crushers: tuple[str, ...] = ("json", "log", "text")
    ccr: bool = True
    ccr_restore: str = "explicit"
    preserve_markers: tuple[str, ...] = DEFAULT_PRESERVE_MARKERS
    metering_tokenizer_path: str | None = None

    @staticmethod
    def from_kwargs(**cfg: object) -> "CompressConfig":
        """Build from the raw dict the CodeRouter loader supplies.

        Unknown keys are ignored (forward-compatible); invalid values fall
        back to safe defaults rather than raising, because a misconfigured
        optional plugin must never take down the router.
        """
        mode = str(cfg.get("mode", "safe")).lower()
        if mode not in VALID_MODES:
            mode = "safe"

        try:
            min_block_tokens = int(cfg.get("min_block_tokens", 200))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            min_block_tokens = 200
        if min_block_tokens < 0:
            min_block_tokens = 0

        targets = _clean_tuple(cfg.get("targets"), VALID_TARGETS, ("tool_result",))
        crushers = _clean_tuple(cfg.get("crushers"), VALID_CRUSHERS, ("json", "log", "text"))

        ccr = bool(cfg.get("ccr", True))

        ccr_restore = str(cfg.get("ccr_restore", "explicit")).lower()
        if ccr_restore not in VALID_RESTORE:
            ccr_restore = "explicit"

        markers_raw = cfg.get("preserve_markers")
        if isinstance(markers_raw, (list, tuple)) and markers_raw:
            preserve_markers = tuple(str(m) for m in markers_raw)
        else:
            preserve_markers = DEFAULT_PRESERVE_MARKERS

        # metering may arrive nested ({"metering": {"tokenizer_path": ...}})
        # or flat (metering_tokenizer_path=...). Accept both.
        tok_path: str | None = None
        metering = cfg.get("metering")
        if isinstance(metering, dict):
            tp = metering.get("tokenizer_path")
            tok_path = str(tp) if tp else None
        elif cfg.get("metering_tokenizer_path"):
            tok_path = str(cfg["metering_tokenizer_path"])

        return CompressConfig(
            mode=mode,
            min_block_tokens=min_block_tokens,
            targets=targets,
            crushers=crushers,
            ccr=ccr,
            ccr_restore=ccr_restore,
            preserve_markers=preserve_markers,
            metering_tokenizer_path=tok_path,
        )


def _clean_tuple(
    value: object, allowed: tuple[str, ...], default: tuple[str, ...]
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        return default
    cleaned = tuple(str(v) for v in value if str(v) in allowed)
    return cleaned or default
