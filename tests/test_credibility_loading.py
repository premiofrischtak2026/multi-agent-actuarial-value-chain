from pathlib import Path

import pytest

from config import ActuarialAssumptions
from pricing.credibility import compose, credibility, k_from_variances
from pricing.engine import PriceEngine
from pricing.loading import compute_loading, theta_from_spread
from pricing.tables import ExposureTable
from schemas import BookingInput

EXPOSURE_HEADER = "year,month,rota,origin_icao,dest_icao,n_voos,freq_cancelamento,freq_chuva_10mm"


def test_credibility_bounds_and_value():
    assert credibility(0, 100) == 0.0
    assert credibility(500, 100) == 1.0
    assert credibility(100, 100) == pytest.approx(0.5)
    assert credibility(1000, 100) == 1.0


def test_k_from_variances():
    assert k_from_variances(10.0, 2.0) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        k_from_variances(1.0, 0.0)


def test_compose():
    assert compose(0.5, 100.0, 200.0) == pytest.approx(150.0)
    assert compose(1.0, 100.0, 200.0) == 100.0
    assert compose(0.0, 100.0, 200.0) == 200.0


def test_theta_from_spread_clipped():
    assert theta_from_spread(0.0) == pytest.approx(0.03)
    assert theta_from_spread(1.0) == pytest.approx(0.12)
    assert 0.03 < theta_from_spread(0.025) < 0.12


def test_loading_default_and_cap():
    a = ActuarialAssumptions()
    result = compute_loading(1000.0, 1_000_000.0, a, theta=0.10)
    assert result.premium_brl == pytest.approx(1000.0 * 1.10 / 0.77, rel=1e-6)
    capped = compute_loading(1000.0, 1000.0, a, theta=0.10)
    assert capped.capped is True
    assert capped.premium_brl == pytest.approx(0.50 * 1000.0)


def test_jericoacoara_commercial_premium_example():
    # artigo 4.7: PP viagem 662,00 (= 66,20 × 10 dias), θ=6,5%, carregamentos 20/5/10, Φ=1,05
    a = ActuarialAssumptions(
        safety_margin=0.065,
        commission=0.20,
        profit=0.05,
        administrative_expense=0.10,
    )
    result = compute_loading(662.0, 100_000.0, a, theta=0.065, multiplier=1.05)
    assert result.premium_brl == pytest.approx(1138.84, abs=1.0)


def _table(tmp_path: Path, rows: list[str]) -> ExposureTable:
    csv = tmp_path / "exposure.csv"
    csv.write_text(EXPOSURE_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return ExposureTable(csv_path=csv)


def _booking(dest="SBPA", date="2025-09-10") -> BookingInput:
    return BookingInput.model_validate(
        {
            "booking_id": "BK-C",
            "flight_date": date,
            "origin_icao": "SBGR",
            "dest_icao": dest,
            "ticket_value_brl": 1000.0,
            "accommodation_value_brl": 500.0,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "x", "start": date, "end": date},
        }
    )


def test_engine_composes_local_and_interpolated(tmp_path):
    table = _table(
        tmp_path,
        [
            "2025,8,SBGR→SBPA,SBGR,SBPA,100,0.01,0.02",
            "2025,9,SBGR→SBFI,SBGR,SBFI,600,0.01,0.03",
            "2025,9,SBGR→SBCT,SBGR,SBCT,600,0.02,0.04",
        ],
    )
    result = PriceEngine(table=table).price(_booking())
    assert result.z_credibilidade is not None and 0.0 < result.z_credibilidade < 1.0
    assert any(s.tipo == "credibilidade" for s in result.fontes)
    assert 0.03 <= result.theta <= 0.12


def test_engine_multiplier_provider_and_bounds(tmp_path):
    table = _table(tmp_path, ["2025,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02"])
    engine = PriceEngine(table=table, multiplier_provider=lambda _b, _m: 99.0)
    result = engine.price(_booking(dest="SBFI"))
    assert result.multiplicador == ActuarialAssumptions().multiplicador_max
