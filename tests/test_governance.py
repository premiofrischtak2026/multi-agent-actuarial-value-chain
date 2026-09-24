import pytest

from governance import Ledger, requires_approval, review
from governance.agents import describe
from governance.hitl import register_override
from graph.workflow import run_flow
from schemas import AcceptanceCode, BookingInput, PricingResult


def _pricing(theta=0.10, premium=100.0) -> PricingResult:
    return PricingResult(
        capital_insured_brl=1000.0,
        freq_cancel=0.01,
        freq_rain_10mm=0.02,
        pure_premium_brl=30.0,
        pure_rate=0.03,
        commercial_rate=0.1,
        premium_brl=premium,
        safety_margin_brl=3.0,
        route_key="SBGR→SBFI",
        theta=theta,
    )


def _booking(**overrides) -> BookingInput:
    payload = {
        "booking_id": "BK-G",
        "flight_date": "2030-09-10",
        "origin_icao": "SBGR",
        "dest_icao": "SBFI",
        "ticket_value_brl": 1000.0,
        "passenger": {"name": "Ana", "document": "1"},
        "stay": {"city": "Foz", "start": "2030-09-10", "end": "2030-09-12"},
    }
    payload.update(overrides)
    return BookingInput.model_validate(payload)


def test_ledger_append_and_verify(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append("sistema", "price", {"premium": 100.0})
    ledger.append("atuario", "override", {"motivo": "caso sensível"})
    assert len(ledger.entries) == 2
    assert ledger.verify() is True
    reloaded = Ledger(tmp_path / "ledger.jsonl")
    assert reloaded.verify() is True


def test_ledger_detects_tampering(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append("sistema", "price", {"premium": 100.0})
    ledger._entries[0].payload["premium"] = 999.0
    assert ledger.verify() is False


def test_auditor_blocks_theta_out_of_range():
    opinion = review(_pricing(theta=0.5))
    assert opinion.bloqueado is True
    assert "θ" in opinion.parecer


def test_auditor_blocks_government_advisory():
    opinion = review(_pricing(theta=0.10), _booking(aviso_governamental=True))
    assert opinion.bloqueado is True


def test_auditor_conforme_with_reservations():
    opinion = review(_pricing(theta=0.10), _booking())
    assert opinion.bloqueado is False
    assert "CONFORME" in opinion.parecer


def test_hitl_requires_approval_and_override():
    assert requires_approval(AcceptanceCode.RH) is True
    assert requires_approval(AcceptanceCode.SI) is True
    assert requires_approval(AcceptanceCode.A) is False
    ledger = Ledger()
    override = register_override(ledger, actor="atuario", motivo="aprovo com ajuste", decisao="A")
    assert override.actor == "atuario"
    assert ledger.entries[-1].action == "override"
    with pytest.raises(ValueError):
        register_override(ledger, actor="x", motivo="  ", decisao="A")


def test_agents_registry():
    names = {a["nome"] for a in describe()}
    assert {"Agente Ingestor", "Agente Auditor"} <= names


def test_regulatory_references_and_ledger():
    from governance import REGULATORY_VERSION
    from governance.regulatory import references

    refs = references()
    assert REGULATORY_VERSION.startswith("REG@")
    codes = {r["codigo"] for r in refs}
    assert {"CIRCULAR_SUSEP_648", "IFRS17", "LEI_15040_2024"} <= codes
    ledger = Ledger()
    run_flow(
        {
            "booking_id": "BK-REG",
            "flight_date": "2030-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBFI",
            "ticket_value_brl": 1000,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "Foz", "start": "2030-09-10", "end": "2030-09-12"},
        },
        ledger=ledger,
    )
    assert any(e.action == "regulatorio" for e in ledger.entries)
    assert ledger.verify() is True


def test_run_flow_records_ledger():
    ledger = Ledger()
    run_flow(
        {
            "booking_id": "BK-L",
            "flight_date": "2030-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBFI",
            "ticket_value_brl": 1000,
            "accommodation_value_brl": 500,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "Foz", "start": "2030-09-10", "end": "2030-09-12"},
        },
        ledger=ledger,
    )
    assert ledger.verify() is True
    assert any(e.action == "price" for e in ledger.entries)
