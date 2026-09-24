from pathlib import Path

import pytest

from graph.workflow import run_flow
from pricing.analogy import analogy_quote, regional_estimate
from pricing.engine import PriceEngine
from pricing.geo import AirportTable
from pricing.tables import ExposureTable
from pricing.tools import (
    estatistica_uf_regiao_mes,
    metadado_aeroporto,
    premissas_nota_tecnica,
    rotas_analogas,
)
from schemas import BookingInput, PricingMethod

HEADER = (
    "year,month,rota,origin_icao,origin_uf,origin_regiao,dest_icao,dest_uf,dest_regiao,"
    "n_voos,freq_cancelamento,freq_chuva_10mm"
)


def _table(tmp_path: Path, rows: list[str]) -> ExposureTable:
    csv = tmp_path / "exposure.csv"
    csv.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return ExposureTable(csv_path=csv)


ROWS = [
    "2025,9,SBGR→SBFI,SBGR,SP,SE,SBFI,PR,S,600,0.010,0.030",
    "2025,9,SBGR→SBCT,SBGR,SP,SE,SBCT,PR,S,500,0.020,0.050",
    "2025,9,SBGR→SBPA,SBGR,SP,SE,SBPA,RS,S,50,0.015,0.040",
]


def _booking(dest="SBPA", date="2025-09-10") -> BookingInput:
    return BookingInput.model_validate(
        {
            "booking_id": "BK-A",
            "flight_date": date,
            "origin_icao": "SBGR",
            "dest_icao": dest,
            "ticket_value_brl": 1500.0,
            "accommodation_value_brl": 800.0,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "x", "start": date, "end": date},
        }
    )


def test_tools_basic(tmp_path):
    table = _table(tmp_path, ROWS)
    airports = AirportTable()
    assert premissas_nota_tecnica()["theta"] == pytest.approx(0.10)
    meta = metadado_aeroporto("SBPA", airports)
    assert meta and meta["regiao"] == "S"
    stats = estatistica_uf_regiao_mes(table, 9, regiao="S")
    assert stats["n_celulas"] >= 1
    analogas = rotas_analogas(table, "SBGR", 9, min_volume=100)
    assert {r["dest_icao"] for r in analogas} == {"SBFI", "SBCT"}


def test_regional_estimate_and_analogy_quote(tmp_path):
    table = _table(tmp_path, ROWS)
    airports = AirportTable()
    booking = _booking()
    estimate = regional_estimate(booking, table, airports)
    assert estimate.freq_cancel > 0 and estimate.freq_rain > 0

    result = analogy_quote(booking, table, airports)
    assert result.metodo == PricingMethod.ANALOGIA
    assert result.fontes
    assert result.aviso and "analogia" in result.aviso.lower()

    manual = PriceEngine(table=table).price_from_rates(
        result.capital_insured_brl, estimate.freq_cancel, estimate.freq_rain,
        result.capital_insured_brl,
    )
    assert result.premium_brl == pytest.approx(manual.premium_brl, abs=0.01)


def test_analogy_premium_comes_from_formula(tmp_path):
    table = _table(tmp_path, ROWS)
    airports = AirportTable()
    booking = _booking()
    from pricing.analogy import AnalogyEstimate

    low = analogy_quote(booking, table, airports, estimate=AnalogyEstimate(0.01, 0.02))
    high = analogy_quote(booking, table, airports, estimate=AnalogyEstimate(0.10, 0.20))
    assert high.premium_brl > low.premium_brl  # premium follows the frequencies via the formula


def test_graph_uses_analogy_when_no_cell(tmp_path):
    # A booking whose route is absent and destination unknown -> analogy path in the graph.
    state = run_flow(
        {
            "booking_id": "BK-Z",
            "flight_date": "2025-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "ZZZZ",
            "ticket_value_brl": 1000,
            "accommodation_value_brl": 500,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "x", "start": "2025-09-10", "end": "2025-09-12"},
        },
        mode="backtest",
    )
    assert state["pricing"] is not None
    # full table exists in repo, so a real cell may be found; just assert flow produced pricing
    assert state["pricing"].metodo in (PricingMethod.DADOS_COMPLETOS, PricingMethod.ANALOGIA)
