from __future__ import annotations

import math
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    generation INTEGER NOT NULL,
    status TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    train_score REAL,
    train_tokens REAL,
    fitness REAL,
    heldout_score REAL,
    focus TEXT,
    meta_variant TEXT,
    delta REAL,
    created_at REAL NOT NULL
);
"""

UPDATABLE = {
    "status",
    "note",
    "train_score",
    "train_tokens",
    "fitness",
    "heldout_score",
    "focus",
    "meta_variant",
    "delta",
}

SELECTIONS = ("open_ended", "greedy")


@dataclass
class AgentRecord:
    id: str
    parent_id: str | None
    generation: int
    status: str
    note: str
    train_score: float | None
    train_tokens: float | None
    fitness: float | None
    heldout_score: float | None
    focus: str | None
    meta_variant: str | None
    delta: float | None
    created_at: float


class Archive:
    """Tree of agent versions. Every valid agent is kept so promising branches can be revisited."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.agents_dir = self.root / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.root / "archive.db")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def genome_dir(self, agent_id: str) -> Path:
        return self.agents_dir / agent_id / "genome"

    def agent_dir(self, agent_id: str) -> Path:
        return self.agents_dir / agent_id

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]

    def new_id(self) -> str:
        return f"a{self.count():04d}"

    def add(
        self,
        agent_id: str,
        parent_id: str | None,
        generation: int,
        status: str,
        note: str = "",
        focus: str | None = None,
        meta_variant: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO agents (id, parent_id, generation, status, note, focus, meta_variant, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                agent_id,
                parent_id,
                generation,
                status,
                note,
                focus,
                meta_variant,
                time.time(),
            ),
        )
        self._conn.commit()

    def update(self, agent_id: str, **fields) -> None:
        unknown = set(fields) - UPDATABLE
        if unknown:
            raise ValueError(f"cannot update fields: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._conn.execute(
            f"UPDATE agents SET {assignments} WHERE id = ?",
            (*fields.values(), agent_id),
        )
        self._conn.commit()

    def get(self, agent_id: str) -> AgentRecord:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            raise KeyError(agent_id)
        return AgentRecord(**dict(row))

    def all(self) -> list[AgentRecord]:
        rows = self._conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
        return [AgentRecord(**dict(r)) for r in rows]

    def children_count(self, agent_id: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM agents WHERE parent_id = ?", (agent_id,)
        ).fetchone()[0]

    def lineage(self, agent_id: str) -> list[AgentRecord]:
        chain = []
        current: str | None = agent_id
        while current is not None:
            record = self.get(current)
            chain.append(record)
            current = record.parent_id
        return list(reversed(chain))

    def best(self) -> AgentRecord | None:
        candidates = [
            a for a in self.all() if a.status == "valid" and a.fitness is not None
        ]
        return max(candidates, key=lambda a: a.fitness) if candidates else None

    def select_parent(
        self, rng: random.Random, strategy: str = "open_ended"
    ) -> AgentRecord:
        """Pick the next parent.

        open_ended: sample with weight sigmoid(10 * (fitness - midpoint)) / (1 + children), where midpoint
        sits between the mean and the maximum fitness. Strong lineages stay in play while under-visited
        branches still get explored.
        greedy: always extend the fittest agent (the hill-climbing control)."""
        if strategy not in SELECTIONS:
            raise ValueError(f"unknown selection strategy: {strategy}")
        candidates = [
            a for a in self.all() if a.status == "valid" and a.fitness is not None
        ]
        if not candidates:
            raise RuntimeError("archive has no evaluated agents")
        if strategy == "greedy":
            return max(
                candidates, key=lambda a: (a.fitness, -self.children_count(a.id))
            )
        scores = [a.fitness for a in candidates]
        midpoint = 0.5 * (max(scores) + sum(scores) / len(scores))
        weights = [
            (1.0 / (1.0 + math.exp(-10.0 * (a.fitness - midpoint))))
            / (1 + self.children_count(a.id))
            for a in candidates
        ]
        return rng.choices(candidates, weights=weights, k=1)[0]
