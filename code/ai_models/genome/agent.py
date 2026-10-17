from __future__ import annotations

import time
from pathlib import Path

from ai_models.llm import BudgetExceeded, LLMClient, Message
from backend.core.sandbox import SandboxConfig
from backend.core.text import clip
from backend.core.trace import RunTrace, Step, ToolRecord

from .prompts import SYSTEM_PROMPT
from .tools import ToolContext, build_tools, execute

CONTEXT_CHAR_LIMIT = 120_000
KEEP_RECENT_MESSAGES = 8


def _brief_args(arguments: dict) -> dict:
    return {k: clip(v, 300) if isinstance(v, str) else v for k, v in arguments.items()}


def _compact(messages: list[Message]) -> None:
    total = sum(len(m.content) for m in messages)
    if total <= CONTEXT_CHAR_LIMIT:
        return
    for m in messages[:-KEEP_RECENT_MESSAGES]:
        if m.role == "tool" and len(m.content) > 200:
            m.content = m.content[:200] + " ...[elided]"


def solve(
    task: str,
    workspace: Path,
    llm: LLMClient,
    sandbox: SandboxConfig,
    max_steps: int = 30,
) -> RunTrace:
    started = time.monotonic()
    tools = build_tools()
    specs = [t.spec for t in tools.values()]
    ctx = ToolContext(workspace=Path(workspace), sandbox=sandbox)
    messages = [Message(role="user", content=task)]
    trace = RunTrace()
    stop = "max_steps"
    last_text = ""

    for index in range(max_steps):
        _compact(messages)
        try:
            response = llm.complete(SYSTEM_PROMPT, messages, specs, 4096)
        except BudgetExceeded:
            stop = "budget"
            break
        except Exception as exc:
            trace.error = clip(f"{type(exc).__name__}: {exc}", 1000)
            stop = "llm_error"
            break

        trace.add_usage(response.usage)
        last_text = response.text or last_text
        messages.append(
            Message(
                role="assistant", content=response.text, tool_calls=response.tool_calls
            )
        )
        step = Step(index=index, text=clip(response.text, 1000))
        trace.steps.append(step)

        if not response.tool_calls:
            stop = "no_tool_calls"
            break

        for call in response.tool_calls:
            output, is_error = execute(tools, ctx, call)
            messages.append(
                Message(
                    role="tool", content=output, tool_call_id=call.id, is_error=is_error
                )
            )
            step.calls.append(
                ToolRecord(
                    call.name, _brief_args(call.arguments), clip(output, 1500), is_error
                )
            )
        if ctx.finished:
            stop = "finished"
            break

    trace.finished = ctx.finished
    trace.final_text = clip(ctx.summary or last_text, 2000)
    trace.stop_reason = stop
    trace.wall_s = round(time.monotonic() - started, 3)
    return trace
