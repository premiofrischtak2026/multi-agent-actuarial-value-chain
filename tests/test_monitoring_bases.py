from datetime import date, datetime, timezone

import pytest

from monitoring.index_monitor import Observation, StaticObservationProvider, evaluate_index
from monitoring.settlement import ppng_pro_rata_die, settle
from schemas import PolicyDocument
from storage import ClaimBase, PolicyBase


def _policy(**overrides) -> PolicyDocument:
    payload = {
        "policy_id": "POL-20300910-000001",
        "booking_id": "BK-8",
        "issued_at": datetime(2030, 9, 1, tzinfo=timezone.utc),
        "effective_start": date(2030, 9, 10),
        "effective_end": date(2030, 9, 15),
        "capital_insured_brl": 2300.0,
        "premium_brl": 100.0,
        "origin_icao": "SBGR",
        "dest_icao": "SBFI",
        "passenger_name": "Ana",
        "ppng_brl": 100.0,
    }
    payload.update(overrides)
    return PolicyDocument.model_validate(payload)


def test_no_trigger_at_exactly_10mm():
    claim = evaluate_index(_policy(), Observation(precip_mm=10.0))
    assert claim.triggered is False
    assert claim.trigger == "none" and claim.status == "closed"


def test_rain_trigger_above_10mm():
    claim = evaluate_index(_policy(), Observation(precip_mm=10.1))
    assert claim.trigger == "rain"
    assert claim.status == "open" and claim.psl_brl == 2300.0
    assert claim.quadro_376["valor_brl"] == 2300.0
    assert claim.sinistro_id == "SIN-POL-20300910-000001"


def test_cancellation_and_both_pay_once():
    cancel = evaluate_index(_policy(), Observation(flight_cancelled=True))
    assert cancel.trigger == "cancellation"
    both = evaluate_index(_policy(), Observation(precip_mm=20.0, flight_cancelled=True))
    assert both.trigger == "both"
    assert both.total_paid_brl == 2300.0  # paid once
    assert both.cancel_paid_brl == 2300.0 and both.rain_paid_brl == 0.0


def test_provider_is_usable():
    provider = StaticObservationProvider(Observation(precip_mm=12.0))
    assert provider.observe(_policy()).precip_mm == 12.0


def test_ppng_pro_rata_die():
    assert ppng_pro_rata_die(100.0, date(2030, 9, 10), date(2030, 9, 20), date(2030, 9, 10)) == 100.0
    assert ppng_pro_rata_die(100.0, date(2030, 9, 10), date(2030, 9, 20), date(2030, 9, 20)) == 0.0
    assert ppng_pro_rata_die(100.0, date(2030, 9, 10), date(2030, 9, 20), date(2030, 9, 15)) == 50.0


def test_bases_persist_and_settle(tmp_path):
    policy_base = PolicyBase(tmp_path / "policies.jsonl")
    claim_base = ClaimBase(tmp_path / "claims.jsonl")

    policy = _policy()
    policy_base.add(policy)
    assert policy_base.get(policy.policy_id)["capital_insured_brl"] == 2300.0

    claim = evaluate_index(policy, Observation(precip_mm=15.0))
    claim_base.add(claim)
    assert claim_base.get(claim.sinistro_id)["status"] == "open"

    result = settle(claim, policy, on_date=date(2030, 9, 12))
    assert result["status"] == "liquidado" and result["psl_brl"] == 0.0
    assert claim_base.settle(claim.sinistro_id) is True
    assert claim_base.get(claim.sinistro_id)["status"] == "liquidado"
    assert policy_base.close(policy.policy_id) is True
