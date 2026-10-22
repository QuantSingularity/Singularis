from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from backend.core.sandbox import SandboxConfig, resolve_in_workspace, run_command
from backend.core.text import clip

from ai_models.llm import ToolCall, ToolSpec

MAX_READ_CHARS = 20_000
MAX_WRITE_CHARS = 200_000
MAX_LIST_ENTRIES = 200
MAX_SEARCH_MATCHES = 100


@dataclass
class ToolContext:
    workspace: Path
    sandbox: SandboxConfig
    finished: bool = False
    summary: str = ""


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    handler: Callable[[ToolContext, dict[str, Any]], str]


def _list_files(ctx: ToolContext, args: dict[str, Any]) -> str:
    root = ctx.workspace.resolve()
    base = resolve_in_workspace(root, str(args.get("path", ".")))
    if not base.exists():
        raise FileNotFoundError(f"no such path: {args.get('path', '.')}")
    if base.is_file():
        return str(base.relative_to(root))
    entries: list[str] = []
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        if path.is_file():
            entries.append(str(rel))
        if len(entries) >= MAX_LIST_ENTRIES:
            entries.append("...(truncated)")
            break
    return "\n".join(entries) or "(empty)"


def _read_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = resolve_in_workspace(ctx.workspace, str(args.get("path", "")))
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {args.get('path')}")
    text = path.read_text(errors="replace")
    start, end = args.get("start_line"), args.get("end_line")
    if start is None and end is None:
        return clip(text, MAX_READ_CHARS)
    lines = text.splitlines()
    first = max(1, int(start or 1))
    last = min(len(lines), int(end or len(lines)))
    if first > last:
        raise ValueError(
            f"line range {first}-{last} is empty (file has {len(lines)} lines)"
        )
    numbered = "\n".join(f"{n}: {lines[n - 1]}" for n in range(first, last + 1))
    return clip(numbered, MAX_READ_CHARS) + f"\n[lines {first}-{last} of {len(lines)}]"


def _write_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = resolve_in_workspace(ctx.workspace, str(args.get("path", "")))
    content = args.get("content")
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    if len(content) > MAX_WRITE_CHARS:
        raise ValueError(f"content exceeds {MAX_WRITE_CHARS} characters")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return f"wrote {len(content)} characters to {args.get('path')}"


def _edit_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = resolve_in_workspace(ctx.workspace, str(args.get("path", "")))
    old, new = args.get("old_str"), args.get("new_str")
    if not isinstance(old, str) or not isinstance(new, str) or old == "":
        raise TypeError(
            "old_str must be a non-empty string and new_str must be a string"
        )
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {args.get('path')}")
    text = path.read_text()
    occurrences = text.count(old)
    if occurrences == 0:
        raise ValueError("old_str not found")
    if occurrences > 1:
        raise ValueError(
            f"old_str matches {occurrences} places, add more context to make it unique"
        )
    path.write_text(text.replace(old, new, 1))
    return f"edited {args.get('path')}"


def _search_text(ctx: ToolContext, args: dict[str, Any]) -> str:
    root = ctx.workspace.resolve()
    base = resolve_in_workspace(root, str(args.get("path", ".")))
    try:
        pattern = re.compile(str(args.get("pattern", "")))
    except re.error as exc:
        raise ValueError(f"invalid regular expression: {exc}")
    files = (
        [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
    )
    matches: list[str] = []
    for path in files:
        rel = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        try:
            lines = path.read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, 1):
            if pattern.search(line):
                matches.append(f"{rel}:{number}: {clip(line, 200)}")
                if len(matches) >= MAX_SEARCH_MATCHES:
                    matches.append("...(truncated)")
                    return "\n".join(matches)
    return "\n".join(matches) or "(no matches)"


def _run_python(ctx: ToolContext, args: dict[str, Any]) -> str:
    argv = args.get("args")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(a, str) for a in argv)
    ):
        raise TypeError("args must be a non-empty list of strings")
    result = run_command([sys.executable, *argv], ctx.workspace, ctx.sandbox)
    status = "timed out" if result.timed_out else f"exit code {result.returncode}"
    return f"{status}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"


def _finish(ctx: ToolContext, args: dict[str, Any]) -> str:
    ctx.finished = True
    ctx.summary = str(args.get("summary", ""))
    return "finished"


def build_tools() -> dict[str, Tool]:
    def spec(
        name: str, description: str, properties: dict, required: list[str]
    ) -> ToolSpec:
        return ToolSpec(
            name,
            description,
            {"type": "object", "properties": properties, "required": required},
        )

    tools = [
        Tool(
            spec(
                "list_files",
                "List files under a directory of the project (default: the project root).",
                {"path": {"type": "string"}},
                [],
            ),
            _list_files,
        ),
        Tool(
            spec(
                "read_file",
                "Read a text file from the project. For large files pass start_line and end_line (1-based, "
                "inclusive) to read a numbered range.",
                {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                ["path"],
            ),
            _read_file,
        ),
        Tool(
            spec(
                "write_file",
                "Create or overwrite a text file in the project with the given content.",
                {"path": {"type": "string"}, "content": {"type": "string"}},
                ["path", "content"],
            ),
            _write_file,
        ),
        Tool(
            spec(
                "edit_file",
                "Replace one exact occurrence of old_str with new_str in a file. Fails if old_str is missing "
                "or appears more than once. Prefer this over rewriting a whole file for small changes.",
                {
                    "path": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                },
                ["path", "old_str", "new_str"],
            ),
            _edit_file,
        ),
        Tool(
            spec(
                "search_text",
                "Search project text files with a regular expression. Returns file:line: text matches.",
                {"pattern": {"type": "string"}, "path": {"type": "string"}},
                ["pattern"],
            ),
            _search_text,
        ),
        Tool(
            spec(
                "run_python",
                "Run the Python interpreter with the given arguments inside the project directory, "
                'for example ["script.py"], ["-m", "unittest"], or ["-c", "print(1)"].',
                {"args": {"type": "array", "items": {"type": "string"}}},
                ["args"],
            ),
            _run_python,
        ),
        Tool(
            spec(
                "finish",
                "Declare the task complete and give a short summary.",
                {"summary": {"type": "string"}},
                ["summary"],
            ),
            _finish,
        ),
    ]
    return {t.spec.name: t for t in tools}


def execute(
    tools: dict[str, Tool], ctx: ToolContext, call: ToolCall
) -> tuple[str, bool]:
    tool = tools.get(call.name)
    if tool is None:
        return f"unknown tool: {call.name}", True
    try:
        return tool.handler(ctx, call.arguments), False
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}", True
