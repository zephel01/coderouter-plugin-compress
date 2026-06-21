"""Process-wide compression stats accumulator.

The filter records savings here as it compresses; the Observer reads and
logs a per-request summary on ``request_completed``. A module-level
singleton is adequate because CodeRouter runs a single async process.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompressionStats:
    requests_seen: int = 0
    blocks_compressed: int = 0
    blocks_restored: int = 0
    original_tokens: int = 0
    compressed_tokens: int = 0
    crusher_counts: dict[str, int] = field(default_factory=dict)

    def record_block(self, crusher: str, orig_tok: int, comp_tok: int) -> None:
        self.blocks_compressed += 1
        self.original_tokens += orig_tok
        self.compressed_tokens += comp_tok
        self.crusher_counts[crusher] = self.crusher_counts.get(crusher, 0) + 1

    def record_restore(self) -> None:
        """A compressed block was re-expanded because a later turn referenced it."""
        self.blocks_restored += 1

    @property
    def saved_tokens(self) -> int:
        return max(0, self.original_tokens - self.compressed_tokens)

    @property
    def ratio(self) -> float:
        if self.original_tokens <= 0:
            return 0.0
        return self.saved_tokens / self.original_tokens

    def snapshot(self) -> dict[str, object]:
        return {
            "requests_seen": self.requests_seen,
            "blocks_compressed": self.blocks_compressed,
            "blocks_restored": self.blocks_restored,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "saved_tokens": self.saved_tokens,
            "ratio": round(self.ratio, 4),
            "crusher_counts": dict(self.crusher_counts),
        }


# Singleton shared by filter + observer.
STATS = CompressionStats()
