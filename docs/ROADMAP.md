# Roadmap

## Implemented

**Foundation.** Baseline agent with six tools, frozen evaluator, sandboxed worker, lineage archive, the
self-modification loop for prompts, tools, and agent logic, a network-isolated container stack, and a lineage
viewer.

**Measurement.**

- 20 tasks in a general, a finance, and an issues track (multi-file bug reports where every fix is required), with
  train, held-out, and fresh splits, all validated against reference solutions.
- SWE-bench style repository tasks: dataset adapter, checkout without git history, test-file reset, FAIL_TO_PASS
  scoring with a regression rule, gold patch validation. Verified on a real git repository in SWE-bench format.
- Repeated trials, bootstrap confidence intervals, paired comparisons, and an `experiment` command that pits
  `open_ended` and `greedy` arms against the unmodified seed.
- Reproducibility manifest and token accounting for meta and evaluation compute.

**Search.**

- Failure clustering in the diagnosis digest, a rotating mutation focus, and open-ended versus greedy parent
  selection.

**Meta level.**

- Evolvable meta prompt with validation and a UCB bandit over variants, rewarded by the fitness change of the
  children they produce.

**Integrity and operations.**

- Static integrity scan with strict, warn, and off modes, HMAC signed records with `verify`, and a live
  localhost dashboard with automatic refresh (tested against the real server in a simulated browser, including
  server loss and recovery).
- Container stack: compose file and Dockerfile validated with official tools, proxy allowlist tested against a
  real squid, `isolation-check` command, and a verification script for machines with Docker.

## Not yet done (needs compute, a model, or a design decision)

1. **Run it.** No live-model run has happened. First priorities: cost per iteration, fraction of children that
   pass validation, and whether fitness moves at all on the builtin suite.
2. **Real SWE-bench data.** The adapter exists but has only been exercised on a synthetic instance. Run it on a
   handful of real Verified instances from one pure Python repository, fix what breaks, then scale. Add per-instance
   environments (the official harness uses one Docker image each) and support for non-pytest runners.
   Terminal-Bench style tasks and a larger finance track (data pipelines, strategy reproduction) remain open.
3. **Stronger controls.** A compute-matched control that spends the same tokens on repeated sampling of the seed,
   and multiple seeds per condition so the confidence intervals reflect search variance, not only task variance.
4. **Richer search.** Crossover between archive branches, novelty scoring on behavior traces, island
   populations, and tool synthesis that must ship with unit tests.
5. **Deeper meta-recursion.** Let the agent propose changes to parent selection and focus scheduling, rewarded
   by the improvement rate of descendants rather than a single child delta.
6. **Run the container stack.** Execute `scripts/verify_docker.sh` on a machine with Docker and fix what it
   finds. Then go further: container-per-task execution and running the hidden tests in a process that never
   loads candidate code, which would close the evaluator forgery path instead of only detecting it.
   Also run `scripts/test_frontend_browser.sh` once for a real Chromium check of the dashboard.
7. **Release.** Preprint and open-source release with full lineages, traces, and signed records.
