from pathlib import Path

import pandas as pd

from config import AIRPORTS_CSV
from pricing.geo import AirportTable, state_to_region

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "data"


def test_airports_csv_exists():
    assert AIRPORTS_CSV.exists(), "run src/scripts/build_airports.py first"


def test_airport_table_basic_lookup():
    table = AirportTable()
    assert len(table) > 100
    sbgr = table.require("SBGR")
    assert sbgr.regiao == "SE"
    assert sbgr.uf == "SP"
    assert -30 < sbgr.lat < 0 and -75 < sbgr.lon < -30
    assert "SBGR" in table
    assert table.get("XXXX") is None


def test_state_to_region():
    assert state_to_region("SP") == "SE"
    assert state_to_region("ce") == "NE"


def test_all_exposure_icaos_have_coordinates():
    exposure = pd.read_parquet(DATA_DIR / "route_month_exposure.parquet", columns=["origin_icao", "dest_icao"])
    needed = {str(v).strip().upper() for col in exposure.columns for v in exposure[col].dropna()}
    table = AirportTable()
    missing = sorted(code for code in needed if code not in table)
    assert not missing, f"ICAOs without metadata: {missing}"
