from pathlib import Path

import pytest

from pricing.calibration import FrequencyModel, calibrate
from pricing.engine import PriceEngine
from pricing.multiplier import seasonal_multiplier
from pricing.tables import ExposureTable
from schemas import BookingInput

HEADER = (
    "year,month,rota,origin_icao,dest_icao,dest_regiao,n_voos,n_cancelados,n_trigger_10mm,"
    "freq_cancelamento,freq_chuva_10mm"
)


def _make_table(tmp_path: Path) -> ExposureTable:
    rows = []
    for month in range(1, 13):
        cancelled = 5 + month
        rain = 10 + month * 3
        rows.append(
            f"2019,{month},SBGR→SBFI,SBGR,SBFI,S,500,{cancelled},{rain},"
            f"{cancelled/500:.4f},{rain/500:.4f}"
        )
    csv = tmp_path / "exposure.csv"
    csv.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return ExposureTable(csv_path=csv)


def test_calibrate_and_predict(tmp_path):
    table = _make_table(tmp_path)
    model = calibrate(table, min_flights=1, path=tmp_path / "m.json")
    cancel_rate, rain_rate = model.predict(month=6, region="S")
    assert cancel_rate >= 0 and rain_rate >= 0
    assert rain_rate > cancel_rate


def test_model_roundtrip(tmp_path):
    table = _make_table(tmp_path)
    model = calibrate(table, min_flights=1, path=tmp_path / "m.json")
    loaded = FrequencyModel.load(tmp_path / "m.json")
    assert loaded is not None
    assert loaded.predict(month=6, region="S") == pytest.approx(model.predict(month=6, region="S"))


def test_engine_uses_glm_for_gap(tmp_path):
    table = _make_table(tmp_path)
    model = calibrate(table, min_flights=1, path=tmp_path / "m.json")
    booking = BookingInput.model_validate(
        {
            "booking_id": "BK-GLM",
            "flight_date": "2019-06-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBCT",
            "ticket_value_brl": 1000.0,
            "accommodation_value_brl": 500.0,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "Curitiba", "start": "2019-06-10", "end": "2019-06-12"},
        }
    )
    engine = PriceEngine(table=table, frequency_model=model, use_interpolation=False)
    result = engine.price(booking)
    assert any(s.tipo == "glm" for s in result.fontes)
    assert result.freq_rain_10mm > 0


def test_seasonal_multiplier_clipped(tmp_path):
    table = _make_table(tmp_path)
    multiplier = seasonal_multiplier(table, month=12, region="S", clip=(0.8, 1.5))
    assert 0.8 <= multiplier <= 1.5
    assert seasonal_multiplier(table, month=6, region="XX", clip=(0.8, 1.5)) >= 0.8
