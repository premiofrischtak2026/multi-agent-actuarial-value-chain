"""Immutable, hash-chained audit ledger (article section 4.8)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _hash(prev_hash: str, payload: dict[str, Any]) -> str:
    blob = prev_hash + json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class LedgerEntry:
    seq: int
    timestamp: str
    actor: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = GENESIS
    hash: str = ""


class Ledger:
    """Append-only ledger; each entry chains the hash of the previous one."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self._entries: list[LedgerEntry] = []
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._entries.append(LedgerEntry(**json.loads(line)))

    @property
    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def _prev_hash(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(self, actor: str, action: str, payload: dict[str, Any] | None = None) -> LedgerEntry:
        prev = self._prev_hash()
        entry = LedgerEntry(
            seq=len(self._entries),
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            action=action,
            payload=payload or {},
            prev_hash=prev,
        )
        entry.hash = _hash(prev, {"seq": entry.seq, "timestamp": entry.timestamp, "actor": actor, "action": action, "payload": entry.payload})
        self._entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def record_state(self, state: dict[str, Any], actor: str = "sistema") -> None:
        for step in state.get("step_log", []):
            action = str(step.get("step", "step"))
            self.append(actor, action, {k: v for k, v in step.items() if k != "step"})

    def verify(self) -> bool:
        prev = GENESIS
        for entry in self._entries:
            expected = _hash(
                prev,
                {"seq": entry.seq, "timestamp": entry.timestamp, "actor": entry.actor, "action": entry.action, "payload": entry.payload},
            )
            if entry.prev_hash != prev or entry.hash != expected:
                return False
            prev = entry.hash
        return True
