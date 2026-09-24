"""Bootstrap: download raw data from public sources and rebuild the artifacts.

The heavy artifacts (flights history, precipitation history, exposure table) are
NOT versioned. This module orchestrates the existing pipeline in ``src/scripts``
so a fresh clone can rebuild them with a single command.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from config import (
    AIRPORTS_CSV,
    CACHE_DIR,
    EXPOSURE_CSV,
    EXPOSURE_PARQUET,
    FLIGHTS_HISTORY_PARQUET,
    PRECIPITATION_HISTORY_PARQUET,
    RAW_DIR,
    WORK_DIR,
)

EXPOSURE_REQUIRED_COLUMNS = frozenset(
    {"year", "month", "rota", "origin_icao", "dest_icao", "freq_cancelamento", "freq_chuva_10mm"}
)


@dataclass
class SyncReport:
    offline: bool
    rebuilt: bool
    ready: bool
    year_start: int
    year_end: int
    missing: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def _exposure_has_columns(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(newline="", encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle), [])
    normalized = {c.lstrip("\ufeff") for c in header}
    return EXPOSURE_REQUIRED_COLUMNS.issubset(normalized)


def missing_artifacts() -> list[str]:
    """Return the list of absent (or invalid) build artifacts."""
    missing: list[str] = []
    if not _exposure_has_columns(EXPOSURE_CSV):
        missing.append(str(EXPOSURE_CSV))
    if not EXPOSURE_PARQUET.exists():
        missing.append(str(EXPOSURE_PARQUET))
    if not FLIGHTS_HISTORY_PARQUET.exists():
        missing.append(str(FLIGHTS_HISTORY_PARQUET))
    if not PRECIPITATION_HISTORY_PARQUET.exists():
        missing.append(str(PRECIPITATION_HISTORY_PARQUET))
    if not AIRPORTS_CSV.exists():
        missing.append(str(AIRPORTS_CSV))
    return missing


def artifacts_ready() -> bool:
    return not missing_artifacts()


def _run(script: str, *, extra_env: dict[str, str] | None = None) -> None:
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    env = {**os.environ, **(extra_env or {})}
    cmd = [sys.executable, script] if script.endswith(".py") else ["bash", script]
    subprocess.run(cmd, cwd=scripts_dir, env=env, check=True)


def run_pipeline(year_start: int, year_end: int) -> None:
    """Download from public sources and rebuild every derived artifact."""
    env = {"YEAR_START": str(year_start), "YEAR_END": str(year_end)}
    _run("download_vra.py", extra_env=env)
    _run("build_flights.py", extra_env=env)
    _run("fetch_precipitation.py", extra_env=env)
    _run("build_exposure.py", extra_env=env)
    _run("build_airports.py")
    _run("build_golden.py")


def sync_data(
    *,
    offline: bool = False,
    force: bool = False,
    year_start: int = 2016,
    year_end: int | None = None,
) -> SyncReport:
    """Ensure the data artifacts exist, rebuilding from public sources if needed.

    - ``offline=True`` never touches the network.
    - ``force=True`` rebuilds even when the artifacts look ready.
    """
    year_end = year_end or date.today().year
    missing = missing_artifacts()
    report = SyncReport(
        offline=offline,
        rebuilt=False,
        ready=not missing,
        year_start=year_start,
        year_end=year_end,
        missing=missing,
    )

    if offline:
        report.messages.append("offline: using existing artifacts / golden sample")
        if missing:
            report.messages.append(f"missing artifacts: {missing}")
        return report

    if not missing and not force:
        report.messages.append("artifacts already present; nothing to do")
        return report

    report.messages.append(f"rebuilding {year_start}-{year_end} from public sources")
    run_pipeline(year_start, year_end)
    report.rebuilt = True
    report.missing = missing_artifacts()
    report.ready = not report.missing
    return report


def cache_directories() -> list[Path]:
    return [RAW_DIR, WORK_DIR, CACHE_DIR]
