"""JSON fixture generation for backtest."""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from config import FIXTURES_DIR
from monitoring.claims import deterministic_outcome
from pricing.tables import load_exposure_csv
from schemas import BookingFixture, Passenger, Stay

SYNTHETIC_NAMES = [
    ("Ana Silva", "12345678901"),
    ("Bruno Costa", "23456789012"),
    ("Carla Mendes", "34567890123"),
    ("Diego Alves", "45678901234"),
    ("Elena Rocha", "56789012345"),
]


def generate_fixtures(
    n: int = 200,
    csv_path: Path | None = None,
    output_dir: Path | None = None,
    seed: int = 42,
) -> list[BookingFixture]:
    from config import EXPOSURE_CSV

    rng = random.Random(seed)
    df = load_exposure_csv(csv_path or EXPOSURE_CSV)
    sample = df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)
    fixtures: list[BookingFixture] = []

    for i, row in sample.iterrows():
        year, month = int(row["year"]), int(row["month"])
        day = rng.randint(1, 28)
        flight_date = date(year, month, day)
        stay_end = flight_date + timedelta(days=rng.randint(2, 5))
        name, doc = SYNTHETIC_NAMES[i % len(SYNTHETIC_NAMES)]
        ticket = round(rng.uniform(400, 2500), 2)
        accommodation = round(rng.uniform(150, 1200), 2)
        excursion = round(rng.uniform(0, 400), 2)
        booking_id = f"BK-{year}{month:02d}-{i:05d}"

        freq_cancel = float(row["freq_cancellation"])
        freq_rain = float(row["freq_rain_10mm"])
        if math.isnan(freq_cancel):
            freq_cancel = 0.05
        if math.isnan(freq_rain):
            freq_rain = 0.15
        outcome = deterministic_outcome(booking_id, freq_cancel, freq_rain)

        fixture = BookingFixture(
            booking_id=booking_id,
            flight_date=flight_date,
            origin_icao=str(row["origin_icao"]),
            dest_icao=str(row["dest_icao"]),
            ticket_value_brl=ticket,
            accommodation_value_brl=accommodation,
            excursion_value_brl=excursion,
            passenger=Passenger(name=name, document=doc),
            stay=Stay(
                city=str(row.get("dest_city", "Destination")),
                start=flight_date,
                end=stay_end,
            ),
            outcome=outcome,
            year=year,
            month=month,
            route=str(row.get("route", "")),
        )
        fixtures.append(fixture)

    out_dir = output_dir or FIXTURES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sample_bookings.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump([f.model_dump(mode="json") for f in fixtures], f, indent=2, ensure_ascii=False)

    return fixtures


if __name__ == "__main__":
    fixtures = generate_fixtures()
    print(f"Generated {len(fixtures)} fixtures at {FIXTURES_DIR / 'sample_bookings.json'}")
