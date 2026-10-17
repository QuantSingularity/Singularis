from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolRecord:
    name: str
    arguments: dict[str, Any]
    output: str
    is_error: bool


@dataclass
class Step:
    index: int
    text: str = ""
    calls: list[ToolRecord] = field(default_factory=list)


@dataclass
class RunTrace:
    steps: list[Step] = field(default_factory=list)
    final_text: str = ""
    finished: bool = False
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    wall_s: float = 0.0
    error: str = ""

    def add_usage(self, usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
