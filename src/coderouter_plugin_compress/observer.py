"""CompressionStatsObserver — passive stats reporter.

Reads the shared STATS accumulator on ``request_completed`` and:

  1. logs a compact human-readable summary (unchanged behaviour), and
  2. emits a neutral ``tokens-saved`` log record that CodeRouter core's
     MetricsCollector aggregates into its token-savings buckets.

The second point is the only coupling to core, and it is *by contract,
not by import*: we emit a ``logging`` record whose message is the event
name ``tokens-saved`` with ``mechanism="compress"`` and a per-request
token delta. CodeRouter attaches its collector to the root logger, so
this record propagates there with no direct dependency on core.

STATS is process-wide cumulative, so we track the last reported
``saved_tokens`` and emit only the increment since the previous
``request_completed`` — this prevents the collector from double-counting
the running total on every request.

Observers must never raise into the engine; all paths swallow errors.
"""
from __future__ import annotations

import logging
from typing import Any

from coderouter_plugin_compress.stats import STATS

_log = logging.getLogger("coderouter_plugin_compress")


class CompressionStatsObserver:
    name = "compress-stats"

    def __init__(self, **_cfg: Any) -> None:
        # Cumulative saved-token high-water mark already reported to core.
        self._last_saved_reported = 0

    async def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type != "request_completed":
            return
        try:
            snap = STATS.snapshot()
            if snap.get("blocks_compressed"):
                _log.info("compress-stats %s", snap)

            # Emit only the delta since the last report (STATS is cumulative).
            saved_total = int(snap.get("saved_tokens", 0))
            delta = saved_total - self._last_saved_reported
            if delta > 0:
                self._last_saved_reported = saved_total
                _log.info(
                    "tokens-saved",
                    extra={
                        "mechanism": "compress",
                        "tokens_saved": delta,
                        # before/after are optional context for the recent ring.
                        "tokens_before": int(snap.get("original_tokens", 0)),
                        "tokens_after": int(snap.get("compressed_tokens", 0)),
                    },
                )
        except Exception:
            # Observers must swallow their own errors.
            return
