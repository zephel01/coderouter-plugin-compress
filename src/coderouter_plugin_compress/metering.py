"""Token measurement for compression stats.

Default backend is the same ``char/4`` heuristic CodeRouter core uses, so
numbers line up with the engine's own estimates. An optional accurate
backend loads a *local* ``tokenizer.json`` via HuggingFace ``tokenizers``
(Rust core) — JSON only, no network, no torch, no pickle — mirroring
CodeRouter's ``token_estimation_accurate`` security stance. If the extra
isn't installed or the path is unreadable, every call transparently falls
back to the heuristic and still returns an ``int``.
"""
from __future__ import annotations

from functools import lru_cache


def heuristic_tokens(text: str) -> int:
    """char/4 estimate. Under-counts CJK (matches CodeRouter core caveat)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@lru_cache(maxsize=8)
def _load_tokenizer(tokenizer_path: str):  # pragma: no cover - exercised when extra present
    """Load a local tokenizer.json, or return None if unavailable.

    Cached so we don't re-read the file on every block. Never contacts the
    network: uses ``Tokenizer.from_file`` exclusively.
    """
    try:
        from tokenizers import Tokenizer  # type: ignore
    except Exception:
        return None
    try:
        return Tokenizer.from_file(tokenizer_path)
    except Exception:
        return None


def count_tokens(text: str, tokenizer_path: str | None = None) -> int:
    """Accurate count when a usable local tokenizer is given, else heuristic."""
    if not text:
        return 0
    if tokenizer_path:
        tok = _load_tokenizer(tokenizer_path)
        if tok is not None:
            try:
                return len(tok.encode(text).ids)
            except Exception:
                pass
    return heuristic_tokens(text)
