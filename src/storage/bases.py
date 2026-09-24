"""Persistent bases for issued policies and claims (JSONL files)."""

from __future__ import annotations

import json
from pathlib import Path

from config import STORAGE_DIR
from schemas import ClaimResult, PolicyDocument


class _JsonlBase:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, payload: dict) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    def update(self, key: str, value: str, changes: dict) -> bool:
        records = self.all()
        updated = False
        for record in records:
            if record.get(key) == value:
                record.update(changes)
                updated = True
        if updated:
            with self.path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return updated


class PolicyBase(_JsonlBase):
    def __init__(self, path: Path | None = None):
        super().__init__(path or (STORAGE_DIR / "policies.jsonl"))

    def add(self, policy: PolicyDocument) -> None:
        self.append(policy.model_dump(mode="json"))

    def get(self, policy_id: str) -> dict | None:
        for record in self.all():
            if record.get("policy_id") == policy_id:
                return record
        return None

    def close(self, policy_id: str, status: str = "closed") -> bool:
        return self.update("policy_id", policy_id, {"status": status})


class ClaimBase(_JsonlBase):
    def __init__(self, path: Path | None = None):
        super().__init__(path or (STORAGE_DIR / "claims.jsonl"))

    def add(self, claim: ClaimResult) -> None:
        self.append(claim.model_dump(mode="json"))

    def get(self, sinistro_id: str) -> dict | None:
        for record in self.all():
            if record.get("sinistro_id") == sinistro_id:
                return record
        return None

    def settle(self, sinistro_id: str) -> bool:
        return self.update("sinistro_id", sinistro_id, {"status": "liquidado", "psl_brl": 0.0})


class DossierBase(_JsonlBase):
    def __init__(self, path: Path | None = None):
        super().__init__(path or (STORAGE_DIR / "dossiers.jsonl"))

    def add(self, policy_id: str, dossier: dict) -> None:
        self.append({"policy_id": policy_id, "dossier": dossier})

    def get(self, policy_id: str) -> dict | None:
        for record in self.all():
            if record.get("policy_id") == policy_id:
                return record.get("dossier")
        return None
