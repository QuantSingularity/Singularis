# frontend

A dependency-free, single-file viewer for evolution runs. No build step and no network access.

## Using it

| Mode          | How                                                                                                                   | Behavior                                                                                                             |
| ------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Static report | `singularis report --root runs/exp1`, open `frontend/index.html`, pick `runs/exp1/report.json` or drop it on the page | Shows a snapshot                                                                                                     |
| Live          | `singularis serve --root runs/exp1`, open the printed address                                                         | Refreshes every 5 seconds, keeps your selection, shows "paused" if the server goes away and recovers when it returns |
| Static host   | Serve the folder over HTTP and open `index.html?report=report.json`                                                   | Loads the file, then refreshes it                                                                                    |

| URL parameter | Default       | Meaning                                        |
| ------------- | ------------- | ---------------------------------------------- |
| `report`      | `report.json` | Path of the report to fetch                    |
| `refresh`     | 5000          | Refresh interval in milliseconds (minimum 200) |

## What the page shows

| Section              | Content                                                                                                               |
| -------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Summary cards        | Agents, valid and invalid counts, best agent, best fitness and held-out score, iterations, meta and evaluation tokens |
| Fitness chart        | Fitness by generation with parent edges; click a point to select an agent                                             |
| Archive table        | Parent, generation, status, train score, fitness, held-out, fitness change, focus, prompt variant, tokens, note       |
| Meta prompt variants | Uses and mean fitness change per variant                                                                              |
| Agent detail         | Notes, train and held-out results per task with integrity flags, and the diff against the parent                      |

Report content comes from agent output, so the page renders everything with `textContent` and never as HTML.

## Files

| Path                              | Purpose                                                                                 |
| --------------------------------- | --------------------------------------------------------------------------------------- |
| `index.html`                      | The whole viewer (HTML, CSS and JavaScript in one file)                                 |
| `sample/report.json`              | Sample data from a scripted run; regenerate with `python scripts/make_sample_report.py` |
| `package.json`                    | Test dependency only (`jsdom`); the viewer itself has no dependencies                   |
| `test/render.js`                  | Render, hostile input and error handling checks                                         |
| `test/live.js`, `test/helpers.js` | Live refresh driver used by the pytest wrapper                                          |
| `test/browser_live.py`            | Real Chromium check through Playwright (not run in the authoring environment)           |

## Tests

| Test                                 | Run with                                               | Environment                     | Status                                           |
| ------------------------------------ | ------------------------------------------------------ | ------------------------------- | ------------------------------------------------ |
| Render and hostile input             | `node test/render.js` (after `npm install`)            | jsdom                           | Verified                                         |
| Live refresh against the real server | `python -m pytest code/backend/tests/test_frontend.py` | jsdom plus the real HTTP server | Verified, mutation checked                       |
| Real browser                         | `scripts/test_frontend_browser.sh`                     | Chromium through Playwright     | Not run yet; also saves `runs/frontend_live.png` |
