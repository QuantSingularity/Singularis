# code

Source root. `pytest.ini` and `pyproject.toml` at the repository root put this directory on the import path, so the
two packages are imported by name (`ai_models`, `backend`).

## Packages

| Package              | Zone          | Contents                                                                                                             |
| -------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------- |
| `ai_models`          | Model side    | `llm.py` (provider interface, Anthropic and scripted clients, budget wrapper) and `genome/` (the agent that evolves) |
| `backend/core`       | Frozen engine | Sandbox, worker, loader, trace, text helpers, logging, isolation checks                                              |
| `backend/evaluation` | Frozen engine | Evaluator, task suites, repository evaluation, SWE-bench adapter, runner, statistics, integrity scan                 |
| `backend/evolution`  | Frozen engine | Archive, evolution loop, meta prompts, experiments, signing, manifest, report, live server                           |
| `backend/cli.py`     | Frozen engine | The `singularis` command                                                                                             |

## Other files

| Path                                 | Purpose                                                                     |
| ------------------------------------ | --------------------------------------------------------------------------- |
| `testkit.py`                         | Scripted-model helpers, ready-made evolver and task helpers shared by tests |
| `conftest.py`                        | pytest fixtures (isolated log directory, script writer)                     |
| `logs/`                              | Runtime logs; override with `SINGULARIS_LOG_DIR`                            |
| `ai_models/tests/`, `backend/tests/` | Tests next to what they test                                                |

## Rules

| Rule                                                                                                                                | Reason                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Only `ai_models/genome/` is modified by the agent                                                                                   | Keeps the evaluator, budgets and selection out of reach    |
| The genome imports only `ai_models.llm`, `backend.core.sandbox`, `backend.core.text`, `backend.core.trace` and the standard library | Keeps the interface contract small and checkable           |
| Inside the genome, use relative imports                                                                                             | The genome is loaded by path under a generated module name |
| `backend` never imports from `ai_models.genome` except to locate the seed genome on disk                                            | Prevents the engine depending on mutable code              |
| Tests live beside the code; shared helpers go in `testkit.py`                                                                       | Keeps fixtures in one place                                |
| No em dashes or emoji in code, docs or deliverables                                                                                 | Project style                                              |

## Adding things

| To add            | Do this                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| A model provider  | Implement `LLMClient.complete` in `ai_models/` and register it in `make_llm`                       |
| Benchmark tasks   | Task directories with `--tasks-dir`, or `Task` objects in a suite module, or SWE-bench data        |
| A mutable surface | Add modules inside `ai_models/genome/`, then update `META_PROMPT` in `backend/evolution/evolve.py` |
| A CLI command     | Add `cmd_*` and a parser entry in `backend/cli.py`, document it in `docs/CLI.md`                   |
