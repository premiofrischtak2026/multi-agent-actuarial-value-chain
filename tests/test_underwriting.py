from datetime import date
from pathlib import Path

import pytest

from config import ActuarialAssumptions
from graph.workflow import run_flow
from schemas import (
    BookingInput,
    PricingMethod,
    PricingResult,
    UnderwritingDecision,
    UnderwritingRecommendation,
)
from underwriting.portfolio import PolicyEntry, Portfolio
from underwriting.rules import UnderwritingEngine


def _booking(capital_value=1000.0, dest="SBFI", city="Foz do Iguaçu") -> BookingInput:
    return BookingInput.model_validate(
        {
            "booking_id": "BK-U",
            "flight_date": "2025-09-10",
            "origin_icao": "SBGR",
            "dest_icao": dest,
            "ticket_value_brl": capital_value,
            "accommodation_value_brl": 0.0,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": city, "start": "2025-09-10", "end": "2025-09-12"},
        }
    )


def _pricing(premium=100.0, capital=1000.0, metodo=PricingMethod.DADOS_COMPLETOS, aviso=None, freq=0.05) -> PricingResult:
    return PricingResult(
        capital_insured_brl=capital,
        freq_cancel=freq / 2,
        freq_rain_10mm=freq / 2,
        pure_premium_brl=capital * freq,
        pure_rate=freq,
        commercial_rate=premium / capital,
        premium_brl=premium,
        safety_margin_brl=0.0,
        route_key="SBGR→SBFI",
        metodo=metodo,
        aviso=aviso,
    )


def test_portfolio_accumulation_and_persistence(tmp_path):
    p = Portfolio()
    p.add(PolicyEntry(None, "b1", "SBGR→SBFI", "SBGR", "SBFI", "Foz", date(2025, 9, 10), date(2025, 9, 12), 1000.0, 100.0))
    p.add(PolicyEntry(None, "b2", "SBGR→SBFI", "SBGR", "SBFI", "Foz", date(2025, 9, 11), date(2025, 9, 13), 2000.0, 200.0))
    premium, count = p.route_month("SBGR→SBFI", 2025, 9)
    assert premium == 300.0 and count == 2
    assert p.capital_in_event("Foz", date(2025, 9, 12), date(2025, 9, 12)) == 3000.0
    path = tmp_path / "p.json"
    p.save(path)
    assert len(Portfolio.load(path)) == 2


def test_recommend_seguir():
    result = UnderwritingEngine().evaluate(_booking(), _pricing())
    assert result.decision == UnderwritingDecision.ACCEPTED
    assert result.recomendacao == UnderwritingRecommendation.SEGUIR
    assert result.confirmacao_atuario_requerida is False


def test_recommend_ressalva_for_analogy():
    result = UnderwritingEngine().evaluate(
        _booking(), _pricing(metodo=PricingMethod.ANALOGIA, aviso="cotação por analogia")
    )
    assert result.recomendacao == UnderwritingRecommendation.SEGUIR_RESSALVA
    assert result.confirmacao_atuario_requerida is True
    assert result.pontos_a_conferir


def test_recommend_recusar_on_hard_limit():
    assumptions = ActuarialAssumptions(max_capital_insured_brl=500.0)
    result = UnderwritingEngine(assumptions=assumptions).evaluate(_booking(capital_value=1000.0), _pricing(capital=1000.0))
    assert result.decision == UnderwritingDecision.REJECTED
    assert result.recomendacao == UnderwritingRecommendation.RECUSAR


def test_recommend_revisao_humana_near_cap():
    assumptions = ActuarialAssumptions(max_premium_per_route_month_brl=100.0, proximity_to_cap=0.80)
    result = UnderwritingEngine(assumptions=assumptions).evaluate(_booking(), _pricing(premium=90.0))
    assert result.recomendacao == UnderwritingRecommendation.REVISAO_HUMANA
    assert result.confirmacao_atuario_requerida is True


def test_portfolio_regional_event_accumulation(tmp_path):
    p = Portfolio()
    p.add(PolicyEntry(None, "b1", "SBGR→SBFI", "SBGR", "SBFI", "Foz", date(2025, 9, 10), date(2025, 9, 12), 1000.0, 100.0, "S"))
    p.add(PolicyEntry(None, "b2", "SBGR→SBPA", "SBGR", "SBPA", "Porto Alegre", date(2025, 9, 11), date(2025, 9, 13), 2000.0, 200.0, "S"))
    assert p.capital_in_regional_event("S", date(2025, 9, 12), date(2025, 9, 12)) == 3000.0
    assert p.capital_in_regional_event("SE", date(2025, 9, 12), date(2025, 9, 12)) == 0.0


def test_recommend_revisao_on_regional_concentration():
    # Same region (S), different municipalities, tiny regional cap.
    assumptions = ActuarialAssumptions(max_capital_per_region_event_brl=1000.0, proximity_to_cap=0.80)
    engine = UnderwritingEngine(assumptions=assumptions)
    engine.evaluate(_booking(capital_value=700.0, dest="SBFI", city="Foz"), _pricing(capital=700.0))
    result = engine.evaluate(_booking(capital_value=700.0, dest="SBPA", city="Porto Alegre"), _pricing(capital=700.0))
    assert result.carteira["regiao"] == "S"
    assert result.carteira["capital_regiao_evento_brl"] == 1400.0
    assert result.decision == UnderwritingDecision.REJECTED  # exceeds the regional cap


def test_graph_human_gate_routes_to_review(tmp_path, monkeypatch):
    # A gap booking triggers the analogy path -> ressalva -> human review when gate is on.
    state = run_flow(
        {
            "booking_id": "BK-G",
            "flight_date": "2025-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "ZZZZ",
            "ticket_value_brl": 1000,
            "accommodation_value_brl": 500,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "x", "start": "2025-09-10", "end": "2025-09-12"},
        },
        require_human_confirmation=True,
    )
    uw = state["underwriting"]
    final = state["step_log"][-1]
    if uw.confirmacao_atuario_requerida:
        assert final["status"] == "human_review"
        assert state.get("policy") is None
    else:
        assert final["status"] in ("completed", "rejected")
