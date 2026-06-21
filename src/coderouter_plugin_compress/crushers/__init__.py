"""Content-type-specific compressors."""
from coderouter_plugin_compress.crushers.base import CrushResult
from coderouter_plugin_compress.crushers.json_crush import crush_json
from coderouter_plugin_compress.crushers.log_crush import crush_log
from coderouter_plugin_compress.crushers.text_crush import crush_text

__all__ = ["CrushResult", "crush_json", "crush_log", "crush_text"]
