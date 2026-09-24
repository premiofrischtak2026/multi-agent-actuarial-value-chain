from datetime import date

import pytest

from criteria import AcceptanceContext, evaluate_acceptance
from criteria.checks import (
    airline_r03,
    consent_and_identity,
    fraud_and_sanctions_r08,
    future_risk_r06,
    hotel_r01_r02,
    legitimate_interest_r07,
    weather_index,
)
from graph.workflow import run_flow
from policy.issuer import PolicyIssuer
from schemas import AcceptanceCode, BookingInput, CriterionStatus, PricingResult

REFERENCE = date(2026, 1, 1)


from underwriting.portfolio import Portfolio


def _context(**kw) -> AcceptanceContext:
    kw.setdefault("portfolio", Portfolio())
    return AcceptanceContext(reference_date=kw.pop("reference_date", REFERENCE), **kw)


def _booking(**overrides) -> BookingInput:
    payload = {
        "booking_id": "BK-AC",
        "flight_date": "2030-09-10",
        "origin_icao": "SBGR",
        "dest_icao": "SBFI",
        "ticket_value_brl": 1500.0,
        "accommodation_value_brl": 800.0,
        "passenger": {"name": "Ana Souza", "document": "123.456.789-09"},
        "stay": {"city": "Foz do Iguaçu", "start": "2030-09-10", "end": "2030-09-15"},
        "consents": {"termos": True, "privacidade": True},
        "hotel": {"cidade": "Foz do Iguaçu", "diarias": 5, "diaria_contratada": 160.0},
        "mediana_comparaveis": 148.0,
        "alta_temporada": True,
        "voucher_no_nome": True,
        "malha_elegivel": True,
        "fonte_indice": "Open-Meteo",
        "indice_cobre_janela": True,
        "fallback_contratado": True,
    }
    payload.update(overrides)
    return BookingInput.model_validate(payload)


def test_consent_deny_without_consents():
    assert consent_and_identity(_booking(consents=None), _context()).resultado == CriterionStatus.DENY


def test_future_risk_denies_past_and_known_event():
    assert future_risk_r06(_booking(), _context(reference_date=date(2031, 1, 1))).resultado == CriterionStatus.DENY
    assert future_risk_r06(_booking(evento_conhecido=True), _context()).resultado == CriterionStatus.DENY


def test_legitimate_interest_denies_third_party():
    assert legitimate_interest_r07(_booking(voucher_no_nome=False), _context()).resultado == CriterionStatus.DENY
    assert legitimate_interest_r07(_booking(voucher_no_nome=None), _context()).resultado == CriterionStatus.INFO


def test_hotel_limit_and_exception():
    assert hotel_r01_r02(_booking(hotel={"cidade": "x", "diarias": 5, "diaria_contratada": 200.0}), _context()).resultado == CriterionStatus.DENY
    assert hotel_r01_r02(_booking(alta_temporada_excepcional=True), _context()).resultado == CriterionStatus.REVIEW
    assert hotel_r01_r02(_booking(), _context()).resultado == CriterionStatus.PASS


def test_airline_and_weather():
    assert airline_r03(_booking(malha_elegivel=False), _context()).resultado == CriterionStatus.DENY
    assert weather_index(_booking(fonte_indice=None), _context()).resultado == CriterionStatus.INFO
    assert weather_index(_booking(indice_cobre_janela=False, fallback_contratado=False), _context()).resultado == CriterionStatus.DENY


def test_fraud_and_sanctions():
    assert fraud_and_sanctions_r08(_booking(sancao=True), _context()).resultado == CriterionStatus.DENY
    assert fraud_and_sanctions_r08(_booking(alerta_fraude=True), _context()).resultado == CriterionStatus.PASS


def test_example_report_04_is_a():
    result = evaluate_acceptance(_booking(), _context())
    assert result.veredito == AcceptanceCode.A
    assert result.politica == "v1.0"


def test_verdict_is_r_when_any_deny():
    denied = evaluate_acceptance(_booking(sancao=True), _context())
    assert denied.veredito == AcceptanceCode.R


def test_verdict_is_si_when_missing_info():
    result = evaluate_acceptance(_booking(fonte_indice=None), _context())
    assert result.veredito == AcceptanceCode.SI


def test_verdict_is_ac_when_fallback_condition():
    result = evaluate_acceptance(_booking(indice_cobre_janela=False, fallback_contratado=True), _context())
    assert result.veredito == AcceptanceCode.AC
    assert result.condicoes


def test_graph_issues_policy_with_conditions_on_ac():
    state = run_flow(
        {
            "booking_id": "BK-AC2",
            "flight_date": "2030-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBFI",
            "ticket_value_brl": 1500,
            "accommodation_value_brl": 800,
            "passenger": {"name": "Ana", "document": "12345678909"},
            "stay": {"city": "Foz do Iguaçu", "start": "2030-09-10", "end": "2030-09-15"},
            "consents": {"termos": True, "privacidade": True},
            "hotel": {"cidade": "Foz do Iguaçu", "diarias": 5, "diaria_contratada": 160},
            "mediana_comparaveis": 148,
            "alta_temporada": True,
            "voucher_no_nome": True,
            "malha_elegivel": True,
            "fonte_indice": "Open-Meteo",
            "indice_cobre_janela": False,
            "fallback_contratado": True,
        },
        mode="backtest",
    )
    assert state["acceptance"].veredito == AcceptanceCode.AC
    assert state.get("policy") is not None
    assert state["policy"].veredito == "AC"
    assert state["policy"].condicoes


def test_audit_gate_blocks_governmental_warning():
    state = run_flow(
        {
            "booking_id": "BK-AUD",
            "flight_date": "2030-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBFI",
            "ticket_value_brl": 1500,
            "accommodation_value_brl": 800,
            "passenger": {"name": "Ana", "document": "12345678909"},
            "stay": {"city": "Foz do Iguaçu", "start": "2030-09-10", "end": "2030-09-15"},
            "consents": {"termos": True, "privacidade": True},
            "hotel": {"cidade": "Foz do Iguaçu", "diarias": 5, "diaria_contratada": 160},
            "mediana_comparaveis": 148,
            "alta_temporada": True,
            "voucher_no_nome": True,
            "malha_elegivel": True,
            "fonte_indice": "Open-Meteo",
            "indice_cobre_janela": True,
            "fallback_contratado": True,
            "aviso_governamental": True,
        },
        mode="backtest",
        audit_gate=True,
    )
    assert state.get("policy") is None
    audit_steps = [entry for entry in state["step_log"] if entry["step"] == "audit"]
    assert audit_steps and audit_steps[0]["bloqueado"] is True


def test_issuer_sets_ppng_and_quadro():
    booking = _booking()
    pricing = PricingResult(
        capital_insured_brl=2300.0,
        freq_cancel=0.01,
        freq_rain_10mm=0.02,
        pure_premium_brl=69.0,
        pure_rate=0.03,
        commercial_rate=0.04,
        premium_brl=92.0,
        safety_margin_brl=6.9,
        route_key="SBGR→SBFI",
    )
    policy = PolicyIssuer().issue(booking, pricing, veredito="A", politica="v1.0")
    assert policy.ppng_brl == 92.0
    assert policy.quadro_378["premio_brl"] == 92.0
    assert policy.janela == "2030-09-10/2030-09-15"
    assert policy.veredito == "A"


def test_graph_accepts_a_complete_booking():
    state = run_flow(
        {
            "booking_id": "BK-G7",
            "flight_date": "2030-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBFI",
            "ticket_value_brl": 1500,
            "accommodation_value_brl": 800,
            "passenger": {"name": "Ana", "document": "12345678909"},
            "stay": {"city": "Foz do Iguaçu", "start": "2030-09-10", "end": "2030-09-15"},
            "consents": {"termos": True, "privacidade": True},
            "hotel": {"cidade": "Foz do Iguaçu", "diarias": 5, "diaria_contratada": 160},
            "mediana_comparaveis": 148,
            "alta_temporada": True,
            "voucher_no_nome": True,
            "malha_elegivel": True,
            "fonte_indice": "Open-Meteo",
            "indice_cobre_janela": True,
            "fallback_contratado": True,
        },
        mode="backtest",
    )
    assert state.get("acceptance") is not None
    assert state["acceptance"].veredito == AcceptanceCode.A
    assert state.get("policy") is not None
    steps = [entry["step"] for entry in state["step_log"]]
    assert "criteria" in steps and "issue" in steps
