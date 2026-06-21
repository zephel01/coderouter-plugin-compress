"""CompressionStatsObserver — passive stats reporter.

Reads the shared STATS accumulator on ``request_completed`` and logs a
compact summary. Tolerates unknown event types (forward-compatible per the
Observer contract). Never raises into the engine.
"""
from __future__ import annotations

import logging
from typing import Any

from coderouter_plugin_compress.stats import STATS

_log = logging.getLogger("coderouter_plugin_compress")


class CompressionStatsObserver:
    name = "compress-stats"

    def __init__(self, **_cfg: Any) -> None:
        pass

    async def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type != "request_completed":
            return
        try:
            snap = STATS.snapshot()
            if snap["blocks_compressed"]:
                _log.info("compress-stats %s", snap)
        except Exception:
            # Observers must swallow their own errors.
            return
