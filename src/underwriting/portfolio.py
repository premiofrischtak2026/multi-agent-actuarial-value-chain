"""Persistent underwriting portfolio: route×month stock and event accumulation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


@dataclass
class PolicyEntry:
    policy_id: str | None
    booking_id: str
    route: str
    origin_icao: str
    dest_icao: str
    municipio: str
    start: date
    end: date
    capital_insured_brl: float
    premium_brl: float
    region: str = ""

    def overlaps(self, other: "PolicyEntry") -> bool:
        return self.start <= other.end and other.start <= self.end


class Portfolio:
    """In-memory portfolio with JSON (de)serialisation for persistence between runs."""

    def __init__(self, entries: list[PolicyEntry] | None = None):
        self._entries: list[PolicyEntry] = list(entries or [])

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> list[PolicyEntry]:
        return list(self._entries)

    def add(self, entry: PolicyEntry) -> None:
        self._entries.append(entry)

    def route_month(self, route: str, year: int, month: int) -> tuple[float, int]:
        premium = 0.0
        count = 0
        for entry in self._entries:
            if entry.route == route and entry.start.year == year and entry.start.month == month:
                premium += entry.premium_brl
                count += 1
        return premium, count

    def capital_in_event(self, municipio: str, start: date, end: date) -> float:
        probe = PolicyEntry("", "", "", "", "", municipio, start, end, 0.0, 0.0)
        total = 0.0
        for entry in self._entries:
            if entry.municipio == municipio and entry.overlaps(probe):
                total += entry.capital_insured_brl
        return total

    def capital_in_regional_event(self, region: str, start: date, end: date) -> float:
        """Conjoint capital across destinations of the same climatic region/basin."""
        if not region:
            return 0.0
        probe = PolicyEntry("", "", "", "", "", "", start, end, 0.0, 0.0)
        total = 0.0
        for entry in self._entries:
            if entry.region == region and entry.overlaps(probe):
                total += entry.capital_insured_brl
        return total

    def to_json(self) -> str:
        return json.dumps([{**asdict(e), "start": e.start.isoformat(), "end": e.end.isoformat()} for e in self._entries], ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "Portfolio":
        raw = json.loads(payload)
        return cls(
            [
                PolicyEntry(**{**item, "start": date.fromisoformat(item["start"]), "end": date.fromisoformat(item["end"])})
                for item in raw
            ]
        )

    def save(self, path: Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Portfolio":
        path = Path(path)
        if not path.exists():
            return cls()
        return cls.from_json(path.read_text(encoding="utf-8"))
