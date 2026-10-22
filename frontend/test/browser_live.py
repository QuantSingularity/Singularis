"""Real browser check of the live dashboard (Chromium via Playwright)."""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

from backend.evolution.archive import Archive
from backend.evolution.serve import make_server
from playwright.sync_api import sync_playwright
from testkit import good_meta_script, make_evolver


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        make_evolver(Path(tmp), good_meta_script()).run()
        root = Path(tmp) / "exp"
        server = make_server(root, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/?refresh=500"
        errors: list[str] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1200, "height": 900})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url)
                page.wait_for_selector("#rows tr")
                assert page.locator("#rows tr").count() == 2

                page.locator("#rows tr").nth(1).click()
                assert page.locator("#rows tr.sel td").first.inner_text() == "a0001"

                archive = Archive(root)
                archive.add(
                    "a0002", "a0001", 2, "valid", "added while the page is open"
                )
                archive.update("a0002", train_score=0.5, fitness=0.5)
                page.wait_for_function(
                    "document.querySelectorAll('#rows tr').length === 3", timeout=10_000
                )
                assert (
                    page.locator("#rows tr.sel td").first.inner_text() == "a0001"
                ), "selection must survive refresh"
                assert page.locator("#status").inner_text().startswith("Live: updated")

                out = ROOT / "runs"
                out.mkdir(exist_ok=True)
                page.screenshot(path=str(out / "frontend_live.png"), full_page=True)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
        assert not errors, f"page errors: {errors}"
    print("browser live refresh ok (screenshot: runs/frontend_live.png)")


if __name__ == "__main__":
    main()
