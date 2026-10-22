"""Regenerate frontend/sample/report.json from a scripted (no API) evolution run."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from backend.evolution.report import write_report
from testkit import dual_meta_script, make_evolver


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evolver = make_evolver(
            Path(tmp), dual_meta_script(), iterations=2, meta_every=1
        )
        evolver.run()
        out = write_report(
            Path(tmp) / "exp", ROOT / "frontend" / "sample" / "report.json"
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
