"""CCR — Compressed-Context Reversibility (phase 2).

Phase 1 added the *safety half*: originals are stashed locally by content
hash so nothing is destroyed. Phase 2 adds **deterministic re-expansion**.

How re-expansion works in a proxy (案A, no MCP tool needed)
----------------------------------------------------------
CodeRouter sits between the client (Claude Code) and the model. The client
keeps its OWN copy of the conversation, so every turn it resends the
*original* uncompressed ``tool_result``. We compress it on the way upstream
and tag it with a CCR id. Crucially the id is ``sha256(original)`` — a pure
function of content — so it is **stable across turns even though we recompute
it every turn.**

The model sees the tag (e.g. ``ccr_ab12...``) and, when it needs the full
output, echoes the id back ("expand ccr_ab12..."). That assistant turn flows
back to the client and, next request, back to us. We scan the inbound
request for referenced ids; any ``tool_result`` whose content hashes to a
referenced id is **passed through uncompressed** that turn. Deterministic,
zero false positives, and it works even with local models that can't call
tools.

The in-process store here backs a future ``coderouter_retrieve`` MCP tool
(案B); the explicit-reference path above does not even require it, because
the client resends the original.
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict

# A CCR id is "ccr_" + 16 lowercase hex chars. This pattern is what we scan
# assistant turns for to detect an explicit expansion request.
CCR_ID_RE = re.compile(r"\bccr_[0-9a-f]{16}\b")


def find_referenced_ids(text: str) -> set[str]:
    """Return every CCR id mentioned in ``text`` (e.g. an assistant turn)."""
    if not text:
        return set()
    return set(CCR_ID_RE.findall(text))


class CCRStore:
    """Bounded, content-addressed store of original block text.

    Eviction is LRU by entry count, with an optional total-byte cap and an
    optional TTL. Local-first and in-process: never written to disk, never
    sent anywhere.
    """

    def __init__(
        self,
        max_entries: int = 512,
        max_bytes: int = 32 * 1024 * 1024,
        ttl_s: float | None = None,
    ) -> None:
        self._max = max_entries
        self._max_bytes = max_bytes
        self._ttl = ttl_s
        # key -> (text, stored_at)
        self._data: "OrderedDict[str, tuple[str, float]]" = OrderedDict()
        self._bytes = 0

    @staticmethod
    def key_for(text: str) -> str:
        return "ccr_" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]

    def put(self, text: str) -> str:
        """Store original text, return its ccr id. Idempotent by content."""
        key = self.key_for(text)
        now = time.monotonic()
        if key in self._data:
            self._data.move_to_end(key)
            self._data[key] = (text, now)
            return key
        size = len(text.encode("utf-8", "replace"))
        self._data[key] = (text, now)
        self._bytes += size
        self._evict()
        return key

    def get(self, key: str) -> str | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        text, stored_at = entry
        if self._ttl is not None and (time.monotonic() - stored_at) > self._ttl:
            self._drop(key)
            return None
        self._data.move_to_end(key)
        return text

    def _drop(self, key: str) -> None:
        entry = self._data.pop(key, None)
        if entry is not None:
            self._bytes -= len(entry[0].encode("utf-8", "replace"))

    def _evict(self) -> None:
        while len(self._data) > self._max or self._bytes > self._max_bytes:
            if not self._data:
                break
            key, (text, _) = self._data.popitem(last=False)
            self._bytes -= len(text.encode("utf-8", "replace"))

    def __len__(self) -> int:
        return len(self._data)
