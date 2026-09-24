"""Airport metadata (ICAO -> city, UF, region, coordinates).

Coordinates are used from Fase 3 on (Haversine / IDW), but the table is
introduced here so every layer shares one source of truth.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import AIRPORTS_CSV

EARTH_RADIUS_KM = 6_367.0

REGION_BY_UF = {
    "AC": "N", "AP": "N", "AM": "N", "PA": "N", "RO": "N", "RR": "N", "TO": "N",
    "AL": "NE", "BA": "NE", "CE": "NE", "MA": "NE", "PB": "NE", "PE": "NE",
    "PI": "NE", "RN": "NE", "SE": "NE",
    "DF": "CO", "GO": "CO", "MT": "CO", "MS": "CO",
    "ES": "SE", "MG": "SE", "RJ": "SE", "SP": "SE",
    "PR": "S", "RS": "S", "SC": "S",
}


@dataclass(frozen=True)
class Airport:
    icao: str
    cidade: str
    uf: str
    regiao: str
    lat: float
    lon: float
    ils_cat: str = ""
    pais: str = ""


def state_to_region(uf: str) -> str:
    code = (uf or "").strip().upper()
    if code not in REGION_BY_UF:
        raise KeyError(f"UF desconhecida: {uf!r}")
    return REGION_BY_UF[code]


class AirportTable:
    """Loads data/airports.csv into an ICAO lookup."""

    def __init__(self, csv_path: Path | None = None):
        self._by_icao: dict[str, Airport] = {}
        self._load(csv_path or AIRPORTS_CSV)

    def _load(self, path: Path) -> None:
        with Path(path).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                icao = (row.get("icao") or "").strip().upper()
                if not icao:
                    continue
                self._by_icao[icao] = Airport(
                    icao=icao,
                    cidade=(row.get("cidade") or "").strip(),
                    uf=(row.get("uf") or "").strip().upper(),
                    regiao=(row.get("regiao") or "").strip().upper(),
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    ils_cat=(row.get("ils_cat") or "").strip(),
                    pais=(row.get("pais") or "").strip(),
                )

    def get(self, icao: str) -> Airport | None:
        return self._by_icao.get((icao or "").strip().upper())

    def require(self, icao: str) -> Airport:
        airport = self.get(icao)
        if airport is None:
            raise KeyError(f"ICAO não encontrado em airports.csv: {icao}")
        return airport

    def __contains__(self, icao: object) -> bool:
        return isinstance(icao, str) and (icao.strip().upper() in self._by_icao)

    def __len__(self) -> int:
        return len(self._by_icao)


@lru_cache(maxsize=1)
def default_airport_table() -> AirportTable:
    return AirportTable()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float, radius_km: float = EARTH_RADIUS_KM) -> float:
    """Great-circle distance (article section 4.3), radius 6,367 km."""
    if radius_km <= 0:
        raise ValueError("O raio da Terra deve ser positivo")
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    sine = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    sine = min(1.0, max(0.0, sine))
    return radius_km * 2.0 * math.atan2(math.sqrt(sine), math.sqrt(1.0 - sine))


def distance_between(a: Airport, b: Airport) -> float:
    return haversine_km(a.lat, a.lon, b.lat, b.lon)
