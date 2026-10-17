# code

Source root. `pytest.ini` and `pyproject.toml` at the repository root put this directory on the import path,
so the two packages below are imported by name (`ai_models`, `backend`).

| Package     | Zone          | Contents                                                                                                                                                                                                                  |
| ----------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ai_models` | model side    | `llm.py` (provider interface, Anthropic client, scripted client, budget wrapper) and `genome/` (the agent that evolves)                                                                                                   |
| `backend`   | frozen engine | `core/` (sandbox, worker, loader, trace, text, logging), `evaluation/` (evaluator, tasks, suites, runner, stats, integrity), `evolution/` (archive, evolve, meta, experiment, signing, manifest, report, serve), `cli.py` |

## Rules of the road

- Only `ai_models/genome/` is ever modified by the agent. Everything else is human-maintained.
- The genome may import `ai_models.llm`, `backend.core.sandbox`, `backend.core.text`, `backend.core.trace`,
  and the standard library. Inside the genome, use relative imports.
- `backend` must never import from `ai_models.genome` except to locate the seed genome on disk.
- Tests live next to what they test (`ai_models/tests`, `backend/tests`). Shared helpers are in `testkit.py`
  and fixtures in `conftest.py`.
- `logs/` receives `singularis.log`. Override the location with `SINGULARIS_LOG_DIR`.

## Adding things

- **LLM provider**: implement `LLMClient.complete` in `ai_models/` and register it in `make_llm`.
- **Benchmark tasks**: see the task directory format in the root README, or add `Task` objects to
  `backend/evaluation/suite.py`.
- **A new mutable surface**: add modules inside `ai_models/genome/`, then update `META_PROMPT` in
  `backend/evolution/evolve.py` so the agent knows it may change them.
