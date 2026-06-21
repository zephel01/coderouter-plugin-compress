"""CompressInputFilter — the engine接点 (InputFilter implementation).

Walks an inbound AnthropicRequest, compresses qualifying content blocks
(tool_result by default), and returns a *new* request via ``model_copy``.

Phase 2 adds **CCR re-expansion** (案A): each compressed block is tagged with
a content-hash id (``ccr_<hex>``). When a later turn in the same request
echoes that id (the model asked to expand it), the block is passed through
uncompressed for that turn. Because the id is a pure function of the original
content and the client resends the original every turn, this is fully
deterministic — no separate retrieval round-trip required.

Contract guarantees (per coderouter.plugins.base.InputFilter):
- Input is treated as immutable; we never mutate the request in place.
- Any failure compressing a block is swallowed and that block is left
  exactly as it was — a broken crusher must never corrupt the request.
- ``mode: off`` is an exact pass-through (returns the same object).
"""
from __future__ import annotations

from typing import Any

from coderouter_plugin_compress.ccr import CCRStore, find_referenced_ids
from coderouter_plugin_compress.config import CompressConfig
from coderouter_plugin_compress.metering import count_tokens
from coderouter_plugin_compress.router import route_and_crush
from coderouter_plugin_compress.stats import STATS

# Don't bother if compression saved fewer than this fraction of chars —
# the CCR marker we add would eat the gain.
_MIN_GAIN = 0.10


class CompressInputFilter:
    """InputFilter that shrinks tool_result blocks before chain dispatch."""

    name = "compress"

    def __init__(self, **cfg: Any) -> None:
        self._cfg = CompressConfig.from_kwargs(**cfg)
        self._ccr = CCRStore() if self._cfg.ccr else None

    async def transform(self, request: Any) -> Any:
        if self._cfg.mode == "off":
            return request

        messages = getattr(request, "messages", None)
        if not messages:
            return request

        STATS.requests_seen += 1

        # Pass 1: collect CCR ids the conversation explicitly references, so
        # we can leave those blocks expanded this turn.
        referenced = self._collect_referenced_ids(messages)

        new_messages = []
        any_change = False
        for msg in messages:
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                new_messages.append(msg)
                continue

            new_blocks, changed = self._compress_blocks(content, referenced)
            if changed:
                any_change = True
                new_messages.append(msg.model_copy(update={"content": new_blocks}))
            else:
                new_messages.append(msg)

        if not any_change:
            return request
        return request.model_copy(update={"messages": new_messages})

    # -- internals -----------------------------------------------------

    def _collect_referenced_ids(self, messages: list[Any]) -> set[str]:
        if self._cfg.ccr_restore == "off":
            return set()
        ids: set[str] = set()
        for msg in messages:
            for txt in _iter_message_text(getattr(msg, "content", None)):
                ids |= find_referenced_ids(txt)
        return ids

    def _compress_blocks(
        self, blocks: list[Any], referenced: set[str]
    ) -> tuple[list[Any], bool]:
        out: list[Any] = []
        changed = False
        for block in blocks:
            new_block = self._maybe_compress_block(block, referenced)
            if new_block is not block:
                changed = True
            out.append(new_block)
        return out, changed

    def _maybe_compress_block(self, block: Any, referenced: set[str]) -> Any:
        if not isinstance(block, dict):
            return block
        if block.get("type") not in self._cfg.targets:
            return block

        text = _extract_text(block.get("content"))
        if text is None:
            return block

        # CCR re-expansion: if this block's id was referenced by a later turn,
        # pass the ORIGINAL through uncompressed this turn.
        cid = CCRStore.key_for(text)
        if cid in referenced:
            STATS.record_restore()
            return block

        tok = self._tok(text)
        if tok < self._cfg.min_block_tokens:
            return block

        try:
            result = route_and_crush(text, self._cfg)
        except Exception:
            # Degraded continue: leave block untouched on any crusher error.
            return block

        if not result.changed:
            return block
        if (len(text) - len(result.text)) / max(1, len(text)) < _MIN_GAIN:
            return block

        comp_tok = self._tok(result.text)
        new_text = result.text
        if self._ccr is not None:
            ccr_id = self._ccr.put(text)  # cid, kept for a future MCP retrieve tool
            new_text = (
                f"{result.text}\n[coderouter-compress {result.crusher}: "
                f"{tok}->{comp_tok} tok; full output id {ccr_id} "
                f'(reply "expand {ccr_id}" to restore)]'
            )

        STATS.record_block(result.crusher, tok, comp_tok)

        new_block = dict(block)
        new_block["content"] = new_text
        return new_block

    def _tok(self, text: str) -> int:
        return count_tokens(text, self._cfg.metering_tokenizer_path)


def _extract_text(content: Any) -> str | None:
    """Pull plain text out of a tool_result block's content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(str(b.get("text", "")))
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts) if parts else None
    return None


def _iter_message_text(content: Any):
    """Yield every text fragment in a message, for CCR-id scanning.

    Covers plain-string messages, text blocks, and the text inside
    tool_result blocks (so a model that echoed an id anywhere is detected).
    """
    if isinstance(content, str):
        yield content
        return
    if isinstance(content, list):
        for b in content:
            if isinstance(b, str):
                yield b
            elif isinstance(b, dict):
                t = b.get("type")
                if t == "text":
                    yield str(b.get("text", ""))
                elif t == "tool_result":
                    inner = _extract_text(b.get("content"))
                    if inner:
                        yield inner
                elif t == "tool_use":
                    # The model's tool call args may carry the id.
                    inp = b.get("input")
                    if isinstance(inp, dict):
                        for v in inp.values():
                            if isinstance(v, str):
                                yield v
