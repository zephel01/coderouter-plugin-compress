"""Test doubles mirroring the AnthropicRequest/Message surface the plugin
duck-types against (``.messages``, ``.content``, ``.model_copy``)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class FakeMessage:
    role: str
    content: Any

    def model_copy(self, update: dict[str, Any] | None = None) -> "FakeMessage":
        update = update or {}
        return replace(self, **update)


@dataclass
class FakeRequest:
    messages: list[FakeMessage] = field(default_factory=list)
    max_tokens: int = 1024

    def model_copy(self, update: dict[str, Any] | None = None) -> "FakeRequest":
        update = update or {}
        base = {"messages": list(self.messages), "max_tokens": self.max_tokens}
        base.update(update)
        return FakeRequest(**base)


def tool_result_msg(text: str, tool_use_id: str = "tu_1") -> FakeMessage:
    return FakeMessage(
        role="user",
        content=[
            {"type": "tool_result", "tool_use_id": tool_use_id, "content": text}
        ],
    )
