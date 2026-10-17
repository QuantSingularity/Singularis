from __future__ import annotations

import json
import math
from pathlib import Path

REQUIRED_PLACEHOLDERS = ("{parent}", "{digest}", "{focus}")
MAX_TEMPLATE_CHARS = 6000
INVALID_REWARD = -0.05
EXPLORATION = 0.1


def validate_template(template: str) -> str | None:
    if len(template) > MAX_TEMPLATE_CHARS:
        return f"template longer than {MAX_TEMPLATE_CHARS} characters"
    missing = [p for p in REQUIRED_PLACEHOLDERS if p not in template]
    if missing:
        return f"missing placeholders: {', '.join(missing)}"
    try:
        template.format(parent="a0000", digest="digest", focus="focus")
    except (KeyError, IndexError, ValueError) as exc:
        return f"template does not format: {exc!r}"
    return None


class MetaPromptStore:
    """Versions of the instruction template used to ask an agent to modify itself.

    Variants are chosen with UCB1 on the fitness change they produced in children, so the process of
    self-improvement is itself subject to selection. Evaluation and selection of agents stay frozen.
    """

    def __init__(self, root: Path, default_template: str):
        self.dir = Path(root) / "meta_prompts"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stats_path = self.dir / "stats.json"
        if not self.stats_path.exists():
            (self.dir / "m0.md").write_text(default_template)
            self._save({"m0": {"uses": 0, "deltas": []}})

    def _load(self) -> dict:
        return json.loads(self.stats_path.read_text())

    def _save(self, stats: dict) -> None:
        self.stats_path.write_text(json.dumps(stats, indent=2))

    def count(self) -> int:
        return len(self._load())

    def template(self, variant_id: str) -> str:
        return (self.dir / f"{variant_id}.md").read_text()

    @staticmethod
    def _mean(deltas: list[float]) -> float:
        return sum(deltas) / len(deltas) if deltas else 0.0

    def choose(self) -> tuple[str, str]:
        stats = self._load()
        untried = sorted(k for k, v in stats.items() if v["uses"] == 0)
        if untried:
            variant = untried[0]
        else:
            total = sum(v["uses"] for v in stats.values())
            variant = max(
                stats,
                key=lambda k: self._mean(stats[k]["deltas"])
                + EXPLORATION * math.sqrt(2 * math.log(total) / stats[k]["uses"]),
            )
        return variant, self.template(variant)

    def record(self, variant_id: str, delta: float) -> None:
        stats = self._load()
        stats[variant_id]["uses"] += 1
        stats[variant_id]["deltas"].append(delta)
        self._save(stats)

    def add_variant(self, template: str) -> tuple[str | None, str]:
        problem = validate_template(template)
        if problem:
            return None, problem
        stats = self._load()
        for existing in stats:
            if self.template(existing).strip() == template.strip():
                return None, "duplicate of an existing variant"
        variant_id = f"m{len(stats)}"
        (self.dir / f"{variant_id}.md").write_text(template)
        stats[variant_id] = {"uses": 0, "deltas": []}
        self._save(stats)
        return variant_id, "ok"

    def best(self) -> str:
        stats = self._load()
        tried = {k: v for k, v in stats.items() if v["uses"] > 0}
        if not tried:
            return "m0"
        return max(tried, key=lambda k: self._mean(tried[k]["deltas"]))

    def summary(self) -> dict:
        return {
            k: {"uses": v["uses"], "mean_delta": self._mean(v["deltas"])}
            for k, v in self._load().items()
        }

    def summary_text(self) -> str:
        lines = [
            f"{k}: used {v['uses']} times, mean fitness change {v['mean_delta']:+.4f}"
            for k, v in self.summary().items()
        ]
        return "\n".join(lines) + "\n"
