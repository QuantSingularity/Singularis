from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    is_error: bool = False


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    stop_reason: str = "end_turn"


class LLMClient(Protocol):
    def complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> LLMResponse: ...


class BudgetExceeded(Exception):
    pass


@dataclass
class Budget:
    max_tokens: int = 400_000
    max_calls: int = 60


class BudgetedClient:
    """Enforces a hard token and call budget around any client."""

    def __init__(self, inner: LLMClient, budget: Budget):
        self._inner = inner
        self.budget = budget
        self.tokens = 0
        self.calls = 0

    def complete(self, system, messages, tools, max_tokens=4096):
        if self.calls >= self.budget.max_calls:
            raise BudgetExceeded("call budget exhausted")
        if self.tokens >= self.budget.max_tokens:
            raise BudgetExceeded("token budget exhausted")
        response = self._inner.complete(system, messages, tools, max_tokens)
        self.calls += 1
        self.tokens += response.usage.input_tokens + response.usage.output_tokens
        return response


def to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for call in m.tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                )
            out.append({"role": "assistant", "content": blocks or "(empty)"})
        elif m.role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m.tool_call_id,
                "content": m.content or "(no output)",
                "is_error": m.is_error,
            }
            last = out[-1] if out else None
            if last and last["role"] == "user" and isinstance(last["content"], list):
                last["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        else:
            raise ValueError(f"unknown role: {m.role}")
    return out


class AnthropicClient:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Install the anthropic extra: pip install 'singularis[anthropic]'"
            ) from exc
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.model = model

    def complete(self, system, messages, tools, max_tokens=4096):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": to_anthropic_messages(messages),
        }
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
        response = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [
            ToolCall(b.id, b.name, dict(b.input))
            for b in response.content
            if b.type == "tool_use"
        ]
        usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
        return LLMResponse(text, calls, usage, response.stop_reason or "")


class ScriptedClient:
    """Deterministic client that replays a fixed script. Used for tests and dry runs."""

    def __init__(self, script: list[dict[str, Any]]):
        self._script = list(script)
        self._index = 0

    @classmethod
    def from_file(cls, path: str | Path) -> "ScriptedClient":
        return cls(json.loads(Path(path).read_text()))

    def complete(self, system, messages, tools, max_tokens=4096):
        if self._index >= len(self._script):
            return LLMResponse(text="script exhausted", usage=Usage(1, 1))
        step = self._script[self._index]
        self._index += 1
        calls = [
            ToolCall(f"call_{self._index}_{i}", c["name"], c.get("arguments", {}))
            for i, c in enumerate(step.get("tool_calls", []))
        ]
        usage = Usage(step.get("input_tokens", 10), step.get("output_tokens", 5))
        return LLMResponse(
            step.get("text", ""), calls, usage, "tool_use" if calls else "end_turn"
        )


def make_llm(spec: str) -> LLMClient:
    kind, _, arg = spec.partition(":")
    if kind == "anthropic":
        return AnthropicClient(model=arg or DEFAULT_MODEL)
    if kind == "scripted":
        return ScriptedClient.from_file(arg)
    raise ValueError(
        f"unknown llm spec: {spec!r} (use 'anthropic:<model>' or 'scripted:<path>')"
    )
