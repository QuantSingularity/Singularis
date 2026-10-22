from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from backend.evolution.archive import Archive

KEY_ENV = "SINGULARIS_SIGNING_KEY"
RESULT_FILES = {
    "results_train_sha256": "results_train.json",
    "results_heldout_sha256": "results_heldout.json",
}


def _key(root: Path) -> bytes:
    from_env = os.environ.get(KEY_ENV)
    if from_env:
        return from_env.encode()
    path = Path(root) / "signing.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    return path.read_text().strip().encode()


def genome_hash(genome: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(genome).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(genome).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def _file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _payload(archive: Archive, agent_id: str) -> dict:
    record = archive.get(agent_id)
    base = archive.agent_dir(agent_id)
    payload = {
        "agent": agent_id,
        "parent": record.parent_id,
        "genome_sha256": genome_hash(archive.genome_dir(agent_id)),
        "train_score": record.train_score,
        "fitness": record.fitness,
        "heldout_score": record.heldout_score,
    }
    for key, filename in RESULT_FILES.items():
        payload[key] = _file_hash(base / filename)
    return payload


def _mac(key: bytes, payload: dict) -> str:
    return hmac.new(
        key, json.dumps(payload, sort_keys=True).encode(), hashlib.sha256
    ).hexdigest()


def sign_agent(root: Path, archive: Archive, agent_id: str) -> Path:
    """Bind an agent's exact code, scores and result files together with an HMAC."""
    payload = _payload(archive, agent_id)
    path = archive.agent_dir(agent_id) / "signature.json"
    path.write_text(
        json.dumps({"payload": payload, "mac": _mac(_key(root), payload)}, indent=2)
    )
    return path


def verify_agent(root: Path, archive: Archive, agent_id: str) -> list[str]:
    path = archive.agent_dir(agent_id) / "signature.json"
    if not path.is_file():
        return ["no signature"]
    try:
        stored = json.loads(path.read_text())
        signed_payload, mac = stored["payload"], stored["mac"]
    except (json.JSONDecodeError, KeyError):
        return ["unreadable signature"]
    problems: list[str] = []
    if not hmac.compare_digest(mac, _mac(_key(root), signed_payload)):
        problems.append(
            "signature does not match its payload (wrong key or edited signature)"
        )
    current = _payload(archive, agent_id)
    for key in sorted(set(current) | set(signed_payload)):
        if current.get(key) != signed_payload.get(key):
            problems.append(f"{key} changed since signing")
    return problems


def verify_all(root: Path, archive: Archive) -> dict[str, list[str]]:
    return {
        record.id: verify_agent(root, archive, record.id)
        for record in archive.all()
        if record.status == "valid"
    }
