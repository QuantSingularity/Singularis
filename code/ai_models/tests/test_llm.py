import pytest

from ai_models.llm import (
    Budget,
    BudgetedClient,
    BudgetExceeded,
    Message,
    ScriptedClient,
    ToolCall,
    make_llm,
    to_anthropic_messages,
)


def test_tool_results_are_grouped_into_one_user_message():
    calls = [ToolCall("1", "a", {}), ToolCall("2", "b", {})]
    messages = [
        Message("user", "go"),
        Message("assistant", "ok", calls),
        Message("tool", "r1", tool_call_id="1"),
        Message("tool", "r2", tool_call_id="2", is_error=True),
    ]
    out = to_anthropic_messages(messages)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    blocks = out[2]["content"]
    assert [b["tool_use_id"] for b in blocks] == ["1", "2"]
    assert blocks[1]["is_error"] is True
    assert [b["type"] for b in out[1]["content"]] == ["text", "tool_use", "tool_use"]


def test_empty_assistant_message_has_content():
    out = to_anthropic_messages([Message("assistant", "")])
    assert out[0]["content"]


def test_scripted_client_replays_and_exhausts():
    client = ScriptedClient(
        [{"text": "a", "tool_calls": [{"name": "t", "arguments": {"x": 1}}]}]
    )
    first = client.complete("", [], [])
    assert first.tool_calls[0].name == "t" and first.tool_calls[0].arguments == {"x": 1}
    assert client.complete("", [], []).text == "script exhausted"


def test_budget_enforced():
    inner = ScriptedClient([{"input_tokens": 60, "output_tokens": 40}] * 5)
    client = BudgetedClient(inner, Budget(max_tokens=150, max_calls=10))
    client.complete("", [], [])
    client.complete("", [], [])
    with pytest.raises(BudgetExceeded):
        client.complete("", [], [])


def test_call_budget_enforced():
    client = BudgetedClient(
        ScriptedClient([{}] * 5), Budget(max_tokens=10**9, max_calls=2)
    )
    client.complete("", [], [])
    client.complete("", [], [])
    with pytest.raises(BudgetExceeded):
        client.complete("", [], [])


def test_make_llm_rejects_unknown():
    with pytest.raises(ValueError):
        make_llm("nonsense:x")
