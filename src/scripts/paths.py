"""Local directories and year range for the data pipeline.

Scripts live next to the application code so a checkout of this folder can
refresh ANAC VRA + Open-Meteo history without the parent monorepo.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PACKAGE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
VRA_DIR = RAW_DIR / "anac_vra"
WORK_DIR = DATA_DIR / "work"
CACHE_DIR = DATA_DIR / "cache_open_meteo"
AIRPORTS_DAT = RAW_DIR / "airports.dat"
AIRLINES_DAT = RAW_DIR / "airlines.dat"

EXPOSURE_CSV = DATA_DIR / "07_Exposicao_Rota_Mes.csv"
EXPOSURE_PARQUET = DATA_DIR / "route_month_exposure.parquet"
FLIGHTS_HISTORY_PARQUET = DATA_DIR / "flights_history_full.parquet"
PRECIPITATION_HISTORY_PARQUET = DATA_DIR / "precipitation_history_full.parquet"

OPENFLIGHTS_AIRPORTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)
OPENFLIGHTS_AIRLINES_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
)
ANAC_VRA_BASE = "https://siros.anac.gov.br/siros/registros/diversos/vra"


def year_range(argv: list[str] | None = None) -> tuple[int, int]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--year-start",
        type=int,
        default=int(os.environ.get("YEAR_START", "2016")),
    )
    parser.add_argument(
        "--year-end",
        type=int,
        default=int(os.environ.get("YEAR_END", str(date.today().year))),
    )
    args, _ = parser.parse_known_args(argv)
    if args.year_end < args.year_start:
        raise SystemExit(f"year-end {args.year_end} < year-start {args.year_start}")
    return args.year_start, args.year_end


def ensure_dirs() -> None:
    for path in (DATA_DIR, RAW_DIR, VRA_DIR, WORK_DIR, CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)
