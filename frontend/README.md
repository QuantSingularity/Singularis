# frontend

A dependency-free, single-file viewer for evolution runs. No build step, no network access.

1. `singularis report --root runs/exp1` writes `runs/exp1/report.json`.
2. Open `frontend/index.html` in a browser and pick the file, or drag it onto the page.

What you get: summary cards, a fitness-by-generation chart with parent edges (click a point to select an
agent), the full archive table, and per agent details with train and held-out task results and the diff
against its parent.

For a live view while an experiment runs, use `singularis serve --root runs/exp1` and open the printed address. The
page refreshes every five seconds and keeps your selection.

To auto-load a static report, serve the files over HTTP and pass its path:

```bash
python -m http.server 8000      # from the directory that contains index.html and report.json
# then open http://localhost:8000/index.html?report=report.json
```

Report content comes from agent output, so the page renders everything with `textContent` and never as HTML.
Tests: `cd frontend && npm install`, then `node test/render.js` or the pytest suite (`code/backend/tests/test_frontend.py`, which
runs the page in jsdom against the real server). `scripts/test_frontend_browser.sh` runs a real Chromium check (Playwright).
`sample/report.json` is sample data from a scripted run; regenerate it with `python scripts/make_sample_report.py`.
