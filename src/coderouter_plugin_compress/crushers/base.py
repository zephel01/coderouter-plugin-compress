"""Shared crusher result type."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrushResult:
    """Outcome of a single crush attempt.

    Attributes:
        text: the compressed text. Equal to the input when ``changed`` is
            False (the crusher decided not to / couldn't help).
        changed: whether the crusher actually shortened the content.
        crusher: name of the crusher that produced this (for stats).
    """

    text: str
    changed: bool
    crusher: str

    @staticmethod
    def unchanged(text: str, crusher: str = "none") -> "CrushResult":
        return CrushResult(text=text, changed=False, crusher=crusher)
