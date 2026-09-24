from pathlib import Path

import pandas as pd

from config import EXPOSURE_GOLDEN_CSV
from data_sync import artifacts_ready, missing_artifacts, sync_data
from data_sync.sources import SOURCES
from pricing.tables import ExposureTable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "src" / "data"


def test_sources_are_documented():
    assert set(SOURCES) >= {"anac_vra", "openflights", "ourairports", "open_meteo"}
    for source in SOURCES.values():
        assert source["url"].startswith("http")


def test_offline_sync_never_rebuilds():
    report = sync_data(offline=True, force=True)
    assert report.offline is True
    assert report.rebuilt is False
    assert isinstance(report.ready, bool)


def test_missing_artifacts_is_a_list():
    missing = missing_artifacts()
    assert isinstance(missing, list)
    assert isinstance(artifacts_ready(), bool)


def test_golden_sample_exists_and_loads():
    assert EXPOSURE_GOLDEN_CSV.exists(), "run src/scripts/build_golden.py"
    df = pd.read_csv(EXPOSURE_GOLDEN_CSV)
    assert len(df) > 0
    assert {"rota", "year", "month", "freq_cancelamento", "freq_chuva_10mm"}.issubset(df.columns)


def test_exposure_table_can_use_golden_sample():
    table = ExposureTable(csv_path=EXPOSURE_GOLDEN_CSV)
    assert len(table.dataframe) > 0
