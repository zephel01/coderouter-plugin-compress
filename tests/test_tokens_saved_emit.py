"""The compress observer emits a per-request ``tokens-saved`` delta.

STATS is cumulative process-wide, so the observer must report only the
increment since the previous ``request_completed`` — otherwise CodeRouter
core would double-count the running total on every request.
"""
from __future__ import annotations

import asyncio
import logging

from coderouter_plugin_compress.observer import CompressionStatsObserver
from coderouter_plugin_compress.stats import STATS


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _setup_capture() -> _Capture:
    cap = _Capture()
    lg = logging.getLogger("coderouter_plugin_compress")
    lg.addHandler(cap)
    lg.setLevel(logging.INFO)
    return cap


def test_observer_emits_only_the_delta() -> None:
    # Reset the process-wide singleton for a deterministic test.
    STATS.requests_seen = 0
    STATS.blocks_compressed = 0
    STATS.original_tokens = 0
    STATS.compressed_tokens = 0
    STATS.crusher_counts = {}

    cap = _setup_capture()
    obs = CompressionStatsObserver()

    # Turn 1: 400 -> 300 (saved 100 cumulative).
    STATS.record_block("json", 400, 300)
    asyncio.run(obs.on_event("request_completed", {}))

    # Turn 2: another 200 -> 120 (saved +80, cumulative 180).
    STATS.record_block("log", 200, 120)
    asyncio.run(obs.on_event("request_completed", {}))

    # Non-completion events are ignored.
    asyncio.run(obs.on_event("request_started", {}))

    saved = [r for r in cap.records if r.msg == "tokens-saved"]
    deltas = [r.__dict__["tokens_saved"] for r in saved]
    assert deltas == [100, 80]
    assert {r.__dict__["mechanism"] for r in saved} == {"compress"}
