from pathlib import Path

from backtest.challenger import compare_methods
from backtest.engine import BacktestEngine
from config import ActuarialAssumptions
from monitoring.indicators import compute_indicators
from pricing.engine import PriceEngine
from pricing.geo import AirportTable
from pricing.impact import repricing_impact
from pricing.tables import ExposureTable
from schemas import BookingInput

HEADER = "year,month,rota,origin_icao,dest_icao,n_voos,freq_cancelamento,freq_chuva_10mm"


def test_backtest_indicators_are_consistent():
    engine = BacktestEngine()
    engine.run(engine.load_fixtures()[:30])
    indicators = compute_indicators(engine.policy_records)
    assert indicators["n"] == 30
    assert indicators["aceitos"] + indicators["recusados"] == 30
    assert 0.0 <= indicators["loss_ratio"] <= 10.0
    assert "qualidade_dados" in indicators and "theta" in indicators


def test_challenger_ranks_methods():
    table = ExposureTable()
    scores = compare_methods(table, AirportTable(), month=9, min_flights=1, k=3)
    methods = {s["metodo"] for s in scores}
    assert {"idw", "nearest", "regional", "kriging"} <= methods
    assert all(s["n"] > 0 for s in scores)
    # ranked by MAE ascending
    assert scores[0]["mae"] <= scores[-1]["mae"]


def test_repricing_impact_detects_change(tmp_path):
    csv = tmp_path / "e.csv"
    csv.write_text(HEADER + "\n2025,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02\n", encoding="utf-8")
    table = ExposureTable(csv_path=csv)
    booking = BookingInput.model_validate(
        {
            "booking_id": "BK-I",
            "flight_date": "2025-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBFI",
            "ticket_value_brl": 1000.0,
            "accommodation_value_brl": 500.0,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "x", "start": "2025-09-10", "end": "2025-09-12"},
        }
    )
    base = PriceEngine(table=table)
    changed = PriceEngine(table=table, assumptions=ActuarialAssumptions(commission=0.25))
    impact = repricing_impact([booking], base, changed)
    assert impact["alterados"] == 1
    assert impact["delta_medio_abs_brl"] > 0
