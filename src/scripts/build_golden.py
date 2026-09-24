#!/usr/bin/env python3
"""Build the committed golden sample of the exposure table.

The sample contains the route×year×month cells used by the backtest fixtures,
so pricing keeps working (offline, no network) when the full exposure table is
not present. Columns keep the Portuguese pipeline headers.
"""

from __future__ import annotations

import csv
import json
import sys

from paths import DATA_DIR, EXPOSURE_CSV

FIXTURES = DATA_DIR.parent / "fixtures" / "backtest" / "sample_bookings.json"
GOLDEN_DIR = DATA_DIR / "golden"
GOLDEN_CSV = GOLDEN_DIR / "exposure_golden_sample.csv"

REQUIRED_COLUMNS = ["year", "month", "rota"]


def _fixture_cells() -> set[tuple[str, int, int]]:
    cells: set[tuple[str, int, int]] = set()
    for booking in json.loads(FIXTURES.read_text(encoding="utf-8")):
        route = f"{booking['origin_icao']}→{booking['dest_icao']}"
        date = booking["flight_date"]
        year = int(booking.get("year") or date[:4])
        month = int(booking.get("month") or date[5:7])
        cells.add((route, year, month))
    return cells


def main(argv: list[str] | None = None) -> None:
    if not EXPOSURE_CSV.exists():
        raise SystemExit(f"Missing {EXPOSURE_CSV}. Run the data pipeline first.")
    cells = _fixture_cells()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    with EXPOSURE_CSV.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise SystemExit(f"Exposure CSV missing columns: {missing}")
        rows = [
            row
            for row in reader
            if (row["rota"], int(row["year"]), int(row["month"])) in cells
        ]

    with GOLDEN_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {GOLDEN_CSV} rows {len(rows)} (of {len(cells)} fixture cells)")


if __name__ == "__main__":
    main()
