"""coderouter-plugin-compress — headroom-inspired context compression.

A CodeRouter InputFilter plugin that compresses tool_result blocks (JSON /
log) before they reach the LLM. Pure-stdlib MVP, opt-in via
``plugins.enabled: [compress]``. Originals are retained locally (CCR) so
nothing is destroyed.
"""
from coderouter_plugin_compress.cache_aligner import (
    CacheAlignConfig,
    CacheAlignInputFilter,
)
from coderouter_plugin_compress.config import CompressConfig
from coderouter_plugin_compress.filter import CompressInputFilter
from coderouter_plugin_compress.observer import CompressionStatsObserver
from coderouter_plugin_compress.router import route_and_crush
from coderouter_plugin_compress.stats import STATS

__version__ = "0.2.0"
__all__ = [
    "CompressInputFilter",
    "CacheAlignInputFilter",
    "CacheAlignConfig",
    "CompressionStatsObserver",
    "CompressConfig",
    "route_and_crush",
    "STATS",
]
