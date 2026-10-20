"""The meter holds the API key and counts tokens, so a rewritten genome can do neither."""

import json
import os
import subprocess
import sys
import textwrap
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from backend.core import meter as meter_module
from backend.core.meter import BUDGET_MARKER, Meter, RunUsage, set_meter, worker_env
from backend.evaluation import runner
from backend.evaluation.runner import (
    RunConfig,
    _worker_env,
    apply_metered_usage,
    run_agent,
)
from backend.evolution.evolve import BUILTIN_GENOME

REAL_KEY = "sk-real-secret-key"


class FakeUpstream:
    """Stands in for api.anthropic.com: records what it receives and answers with a fixed usage."""

    def __init__(self, usage=(100, 20), content=None):
        self.requests = []
        self.usage = usage
        self.content = content or [{"type": "text", "text": "hi"}]
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                upstream.requests.append(
                    {
                        "key": self.headers.get("x-api-key"),
                        "path": self.path,
                        "body": json.loads(body),
                    }
                )
                reply = json.dumps(
                    {
                        "content": upstream.content,
                        "stop_reason": "end_turn",
                        "usage": {
                            "input_tokens": upstream.usage[0],
                            "output_tokens": upstream.usage[1],
                        },
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def upstream():
    fake = FakeUpstream()
    yield fake
    fake.close()


@pytest.fixture
def meter(upstream):
    m = Meter(upstream=upstream.url, api_key=REAL_KEY)
    yield m
    m.stop()


def post(url, body=None, path="/v1/messages", key="metered"):
    request = urllib.request.Request(
        url + path,
        data=json.dumps(body or {"model": "m", "messages": []}).encode(),
        headers={"content-type": "application/json", "x-api-key": key},
    )
    try:
        with urllib.request.urlopen(request) as reply:
            return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_tokens_are_counted_from_what_the_api_reports(meter):
    run = meter.open_run(10_000, 10)
    for _ in range(3):
        assert post(meter.base_url(run))[0] == 200
    assert meter.close_run(run) == RunUsage(300, 60, 3)


def test_the_real_key_is_used_upstream_and_the_clients_key_is_ignored(meter, upstream):
    run = meter.open_run(10_000, 10)
    post(meter.base_url(run), key="whatever-the-genome-sends")
    assert [r["key"] for r in upstream.requests] == [REAL_KEY]


def test_token_budget_is_enforced_by_the_meter(meter):
    run = meter.open_run(max_tokens=150, max_calls=99)
    assert post(meter.base_url(run))[0] == 200  # 120 used
    assert (
        post(meter.base_url(run))[0] == 200
    )  # 240 used, over budget but each call is allowed to finish
    status, body = post(meter.base_url(run))
    assert status == 403 and BUDGET_MARKER in body["error"]["message"]
    assert meter.close_run(run).calls == 2  # the refused call never reached the API


def test_call_budget_is_enforced_by_the_meter(meter, upstream):
    run = meter.open_run(max_tokens=10**9, max_calls=2)
    statuses = [post(meter.base_url(run))[0] for _ in range(4)]
    assert statuses == [200, 200, 403, 403] and len(upstream.requests) == 2


def test_runs_cannot_spend_each_others_budgets(meter):
    first, second = meter.open_run(10**6, 10), meter.open_run(10**6, 10)
    post(meter.base_url(first))
    assert meter.close_run(second).calls == 0
    assert post(meter.base_url("guessed-id"))[0] == 404


def test_a_closed_run_is_gone(meter):
    run = meter.open_run(10**6, 10)
    meter.close_run(run)
    assert post(meter.base_url(run))[0] == 404


def test_unsupported_requests_are_refused(meter):
    run = meter.open_run(10**6, 10)
    assert post(meter.base_url(run), {"stream": True})[0] == 400
    assert post(meter.base_url(run), path="/v1/models")[0] == 404


def test_a_worker_environment_holds_no_secrets(meter, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", REAL_KEY)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    run = meter.open_run(10, 10)
    env = _worker_env(RunConfig(llm_spec="anthropic:m"), worker_env(meter, run))
    assert REAL_KEY not in "".join(env.values())
    assert "HTTPS_PROXY" not in env and env["ANTHROPIC_API_KEY"] == "metered"
    assert env["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:")


def test_key_file_is_preferred_over_the_environment(tmp_path, monkeypatch):
    key_file = tmp_path / "key"
    key_file.write_text("sk-from-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    monkeypatch.setenv("ANTHROPIC_API_KEY_FILE", str(key_file))
    assert meter_module.load_api_key() == "sk-from-file"


def test_self_reported_tokens_are_replaced_and_misreports_are_flagged():
    honest = {"input_tokens": 100, "output_tokens": 20}
    apply_metered_usage(honest, RunUsage(100, 20, 1))
    assert honest["token_report_mismatch"] is False
    liar = {"input_tokens": 0, "output_tokens": 0}
    apply_metered_usage(liar, RunUsage(500, 100, 3))
    assert (liar["input_tokens"], liar["output_tokens"]) == (500, 100)
    assert liar["token_report_mismatch"] is True and liar["reported_tokens"] == 0


def test_the_budget_refusal_becomes_budget_exceeded(monkeypatch):
    from ai_models.llm import AnthropicClient, BudgetExceeded

    class Messages:
        def create(self, **kwargs):
            raise Exception(f"Error code: 403 - {BUDGET_MARKER}: token budget spent")

    stub = SimpleNamespace(Anthropic=lambda **kw: SimpleNamespace(messages=Messages()))
    monkeypatch.setitem(sys.modules, "anthropic", stub)
    with pytest.raises(BudgetExceeded):
        AnthropicClient("m").complete("s", [], [])


# ---- the process-level protection ----------------------------------------------------------------

DUMP_PROBE = textwrap.dedent(
    """
    import ctypes, os, subprocess, sys
    if sys.argv[1] == "harden":
        ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)
    child = f"open('/proc/{os.getpid()}/environ').read()"
    r = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True)
    print("DENIED" if "Permission" in r.stderr else "READABLE")
    """
)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
def test_a_non_dumpable_parent_hides_its_environment_from_a_same_user_child():
    def run(mode):
        def drop():  # root can read everything, so test as an ordinary user
            os.setgid(65534)
            os.setuid(65534)

        kwargs = {"preexec_fn": drop} if os.geteuid() == 0 else {}
        out = subprocess.run(
            [sys.executable, "-c", DUMP_PROBE, mode],
            capture_output=True,
            text=True,
            cwd="/",
            **kwargs,
        )
        return out.stdout.strip()

    if run("plain") != "READABLE":
        pytest.skip("cannot establish the unprotected baseline in this environment")
    assert run("harden") == "DENIED"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
def test_harden_process_clears_the_dumpable_flag(tmp_path):
    code = (
        "import ctypes\nfrom backend.core.meter import harden_process\n"
        "ok = harden_process()\nprint(ok, ctypes.CDLL(None).prctl(3, 0, 0, 0, 0))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(runner.SRC_ROOT)},
    )
    assert out.stdout.split() == ["True", "0"], out.stderr


# ---- end to end: a real worker process talking to a fake API through the meter ---------------------

STUB_SDK = textwrap.dedent(
    """
    import json, os, urllib.request
    from types import SimpleNamespace as NS

    class _Messages:
        def create(self, **kwargs):
            seen = {k: v for k, v in os.environ.items() if "KEY" in k or "PROXY" in k}
            open("__DUMP__", "w").write(json.dumps(seen))
            request = urllib.request.Request(
                os.environ["ANTHROPIC_BASE_URL"] + "/v1/messages",
                data=json.dumps({"model": kwargs["model"], "messages": []}).encode(),
                headers={"content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"]},
            )
            data = json.loads(urllib.request.urlopen(request).read())
            blocks = [
                NS(type=b["type"], id=b.get("id"), name=b.get("name"), input=b.get("input", {}), text=b.get("text", ""))
                for b in data["content"]
            ]
            return NS(content=blocks, usage=NS(**data["usage"]), stop_reason=data["stop_reason"])

    class Anthropic:
        def __init__(self, api_key=None, **kw):
            self.messages = _Messages()
    """
)


@pytest.fixture
def live_path(tmp_path, monkeypatch, upstream):
    """A worker that imports a stub `anthropic`, a fake API that answers with a `finish` call, a real meter."""
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    dump = tmp_path / "env_dump.json"
    (sdk / "anthropic.py").write_text(STUB_SDK.replace("__DUMP__", str(dump)))
    monkeypatch.setenv("ANTHROPIC_API_KEY", REAL_KEY)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    monkeypatch.setattr(runner, "SRC_ROOT", f"{runner.SRC_ROOT}{os.pathsep}{sdk}")
    upstream.content = [
        {"type": "tool_use", "id": "t1", "name": "finish", "input": {"summary": "done"}}
    ]
    real = Meter(upstream=upstream.url)
    set_meter(real)
    yield SimpleNamespace(dump=dump, upstream=upstream)
    set_meter(None)
    real.stop()


def _agent(tmp_path, genome):
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    cfg = RunConfig(llm_spec="anthropic:stub-model", wall_timeout_s=60)
    return run_agent(genome, workspace, "do it", cfg, tmp_path / "out", "t")


def test_a_real_worker_runs_through_the_meter_without_ever_seeing_the_key(
    tmp_path, live_path
):
    trace, _ = _agent(tmp_path, BUILTIN_GENOME)
    seen = json.loads(live_path.dump.read_text())
    assert trace["stop_reason"] == "finished", trace.get("error")
    assert (trace["input_tokens"], trace["output_tokens"], trace["metered_calls"]) == (
        100,
        20,
        1,
    )
    assert trace["token_report_mismatch"] is False
    # a placeholder key and the loopback bypass only: no real key, no HTTPS_PROXY / HTTP_PROXY
    assert seen == {"ANTHROPIC_API_KEY": "metered", "NO_PROXY": "127.0.0.1,localhost"}
    assert [r["key"] for r in live_path.upstream.requests] == [REAL_KEY]


def test_a_genome_that_under_reports_its_tokens_is_overruled_and_flagged(
    tmp_path, live_path
):
    import shutil

    cheat = tmp_path / "cheat_genome"
    shutil.copytree(BUILTIN_GENOME, cheat, ignore=shutil.ignore_patterns("__pycache__"))
    agent = cheat / "agent.py"
    agent.write_text(
        agent.read_text().replace("trace.add_usage(response.usage)", "pass")
    )
    trace, _ = _agent(tmp_path, cheat)
    assert trace["reported_tokens"] == 0
    assert (trace["input_tokens"], trace["output_tokens"]) == (
        100,
        20,
    )  # the meter's numbers win
    assert trace["token_report_mismatch"] is True
