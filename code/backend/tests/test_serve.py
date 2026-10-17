import json
import threading
import urllib.error
import urllib.request

import pytest
from backend.evolution.serve import make_server
from testkit import good_meta_script, make_evolver


@pytest.fixture
def server(tmp_path):
    make_evolver(tmp_path, good_meta_script()).run()
    srv = make_server(tmp_path / "exp", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.headers, response.read()


def test_live_report_reflects_the_archive(server):
    status, headers, body = get(server + "/report.json")
    report = json.loads(body)
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert {a["id"] for a in report["agents"]} == {"a0000", "a0001"}
    assert report["usage"]["iterations"] == 1 and "m0" in report["meta_prompts"]


def test_index_and_health_routes(server):
    status, headers, body = get(server + "/")
    assert (
        status == 200
        and b"Singularis" in body
        and "text/html" in headers["Content-Type"]
    )
    assert get(server + "/healthz")[2] == b"ok"


def test_unknown_and_traversal_paths_are_404(server):
    for path in (
        "/nope",
        "/../../etc/passwd",
        "/archive.db",
        "/agents/a0000/genome/agent.py",
    ):
        with pytest.raises(urllib.error.HTTPError) as error:
            get(server + path)
        assert error.value.code == 404


def test_refuses_remote_bind_without_opt_in(tmp_path):
    with pytest.raises(ValueError):
        make_server(tmp_path, host="0.0.0.0", port=0)
