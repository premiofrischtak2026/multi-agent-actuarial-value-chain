"""LangGraph graph — full travel insurance flow."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from criteria import AcceptanceContext, evaluate_acceptance
from governance.auditor import review as audit_pricing
from graph.state import GraphState
from llm import get_chat_model, llm_available
from monitoring.claims import ClaimsEngine
from policy.issuer import PolicyIssuer
from pricing.analogy import analogy_quote
from pricing.engine import PriceEngine
from pricing.geo import default_airport_table
from schemas import AcceptanceCode, BookingFixture, UnderwritingDecision
from underwriting.rules import UnderwritingEngine

_price_engine = PriceEngine()
_underwriting = UnderwritingEngine()
_issuer = PolicyIssuer()
_claims = ClaimsEngine()


def _log(state: GraphState, step: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    log = list(state.get("step_log") or [])
    log.append({"step": step, **payload})
    return log


def _extract_from_dict(raw: dict[str, Any], mode: str) -> BookingFixture:
    if mode == "manual" and llm_available():
        llm = get_chat_model()
        prompt = (
            "Extract travel booking fields from the JSON/text below. "
            "Return valid JSON only with: booking_id, flight_date, origin_icao, "
            "dest_icao, ticket_value_brl, excursion_value_brl, passenger {name, document}, "
            "stay {city, start, end}.\n\n"
            f"{json.dumps(raw, ensure_ascii=False)}"
        )
        response = llm.invoke(
            [
                SystemMessage(content="You extract structured booking data."),
                HumanMessage(content=prompt),
            ]
        )
        try:
            return BookingFixture.model_validate(json.loads(response.content))
        except (json.JSONDecodeError, ValueError):
            return BookingFixture.model_validate(raw)
    return BookingFixture.model_validate(raw)


def make_extract_node(mailbox=None, document_extractor=None, booking_extractor=None, artifact_dir=None):
    """Build the extract node. If a mailbox is injected, ingest from e-mail/PDF."""

    def extract_node(state: GraphState) -> GraphState:
        mode = state.get("mode", "backtest")
        raw = state.get("booking")
        if raw is None and mailbox is not None:
            from ingestion import PdfTextExtractor, ingest_next, save_artifacts
            from ingestion.extraction_agent import LLMBookingExtractor, StubBookingExtractor

            extractor = document_extractor or PdfTextExtractor()
            if booking_extractor is not None:
                booking_extractor_impl = booking_extractor
            elif llm_available():
                booking_extractor_impl = LLMBookingExtractor()
            else:
                booking_extractor_impl = StubBookingExtractor()

            result = ingest_next(
                mailbox,
                document_extractor=extractor,
                booking_extractor=booking_extractor_impl,
            )
            if result is None:
                return {
                    "error": "mailbox_empty",
                    "step_log": _log(state, "extract", {"status": "mailbox_empty"}),
                }
            if artifact_dir is not None:
                try:
                    save_artifacts(result, artifact_dir)
                except OSError:
                    pass
            if not result.ok:
                return {
                    "error": "missing_fields",
                    "missing_fields": result.missing,
                    "step_log": _log(
                        state, "extract", {"status": "missing_fields", "missing": result.missing}
                    ),
                }
            booking = result.booking
            assert booking is not None
        else:
            booking = _extract_from_dict(raw or {}, mode)

        return {
            "booking_model": booking,
            "step_log": _log(state, "extract", {"booking_id": booking.booking_id}),
        }

    return extract_node


def after_extract(state: GraphState) -> str:
    return "end_error" if state.get("error") else "price"


extract_node = make_extract_node()


def _has_local_data(pricing) -> bool:
    return not any(s.tipo == "fallback" and s.ref == "defaults" for s in pricing.fontes)


def price_node(state: GraphState) -> GraphState:
    booking = state["booking_model"]
    assert booking is not None
    mode = state.get("mode", "backtest")

    pricing = _price_engine.price(booking)
    if not _has_local_data(pricing):
        try:
            pricing = analogy_quote(
                booking, _price_engine.table, default_airport_table(), engine=_price_engine
            )
        except (FileNotFoundError, OSError):
            pass

    if mode == "manual" and llm_available():
        llm = get_chat_model()
        explanation = llm.invoke(
            [
                SystemMessage(
                    content="Explain travel insurance pricing decisions concisely in English."
                ),
                HumanMessage(content=pricing.explanation),
            ]
        )
        pricing = pricing.model_copy(update={"explanation": explanation.content})

    return {
        "pricing": pricing,
        "step_log": _log(state, "price", pricing.model_dump()),
    }


def underwrite_node(state: GraphState) -> GraphState:
    booking = state["booking_model"]
    pricing = state["pricing"]
    assert booking is not None and pricing is not None
    mode = state.get("mode", "backtest")

    uw = _underwriting.evaluate(booking, pricing)
    if mode == "manual" and llm_available() and uw.decision == UnderwritingDecision.REJECTED:
        llm = get_chat_model()
        msg = llm.invoke(
            [
                SystemMessage(
                    content="Rewrite underwriting rejection reasons for the customer, in English."
                ),
                HumanMessage(content=uw.reason),
            ]
        )
        uw = uw.model_copy(update={"reason": msg.content})

    return {
        "underwriting": uw,
        "step_log": _log(state, "underwrite", uw.model_dump()),
    }


def should_issue(state: GraphState) -> str:
    uw = state.get("underwriting")
    if not uw or uw.decision != UnderwritingDecision.ACCEPTED:
        return "end_rejected"
    if state.get("require_human_confirmation") and uw.confirmacao_atuario_requerida:
        return "end_review"
    return "criteria"


def criteria_node(state: GraphState) -> GraphState:
    booking = state["booking_model"]
    assert booking is not None
    context = AcceptanceContext(reference_date=date.today(), portfolio=_underwriting.portfolio)
    acceptance = evaluate_acceptance(booking, context)
    return {
        "acceptance": acceptance,
        "step_log": _log(state, "criteria", acceptance.model_dump(mode="json")),
    }


def after_criteria(state: GraphState) -> str:
    acceptance = state.get("acceptance")
    if acceptance is None:
        return "end_rejected"
    if acceptance.veredito in (AcceptanceCode.A, AcceptanceCode.AC):
        return "audit" if state.get("require_audit") else "issue"
    if acceptance.veredito in (AcceptanceCode.RH, AcceptanceCode.SI):
        return "end_review"
    return "end_rejected"


def audit_node(state: GraphState) -> GraphState:
    booking = state["booking_model"]
    pricing = state["pricing"]
    assert booking is not None and pricing is not None
    opinion = audit_pricing(pricing, booking)
    return {
        "audit": opinion,
        "step_log": _log(
            state,
            "audit",
            {"bloqueado": opinion.bloqueado, "motivos": opinion.motivos, "parecer": opinion.parecer},
        ),
    }


def after_audit(state: GraphState) -> str:
    opinion = state.get("audit")
    if opinion is not None and opinion.bloqueado:
        return "end_rejected"
    return "issue"


def issue_node(state: GraphState) -> GraphState:
    booking = state["booking_model"]
    pricing = state["pricing"]
    acceptance = state.get("acceptance")
    assert booking is not None and pricing is not None
    policy = _issuer.issue(
        booking,
        pricing,
        veredito=acceptance.veredito.value if acceptance else None,
        politica=acceptance.politica if acceptance else None,
        condicoes=acceptance.condicoes if acceptance else None,
    )
    return {
        "policy": policy,
        "step_log": _log(state, "issue", policy.model_dump(mode="json")),
    }


def monitor_claim_node(state: GraphState) -> GraphState:
    booking = state["booking_model"]
    policy = state["policy"]
    pricing = state["pricing"]
    assert booking is not None and policy is not None and pricing is not None
    claim = _claims.evaluate(policy, booking, pricing.freq_cancel, pricing.freq_rain_10mm)
    return {
        "claim": claim,
        "step_log": _log(state, "claim", claim.model_dump()),
    }


def end_rejected_node(state: GraphState) -> GraphState:
    return {"step_log": _log(state, "end", {"status": "rejected"})}


def end_review_node(state: GraphState) -> GraphState:
    uw = state.get("underwriting")
    return {
        "step_log": _log(
            state,
            "end",
            {
                "status": "human_review",
                "recomendacao": uw.recomendacao.value if uw else None,
                "pontos_a_conferir": uw.pontos_a_conferir if uw else [],
            },
        )
    }


def end_error_node(state: GraphState) -> GraphState:
    payload: dict[str, Any] = {"status": "error", "error": state.get("error")}
    if state.get("missing_fields"):
        payload["missing_fields"] = state["missing_fields"]
    return {"step_log": _log(state, "end", payload)}


def build_graph(mailbox=None, document_extractor=None, booking_extractor=None, artifact_dir=None):
    graph = StateGraph(GraphState)
    graph.add_node(
        "extract", make_extract_node(mailbox, document_extractor, booking_extractor, artifact_dir)
    )
    graph.add_node("price", price_node)
    graph.add_node("underwrite", underwrite_node)
    graph.add_node("criteria", criteria_node)
    graph.add_node("audit", audit_node)
    graph.add_node("issue", issue_node)
    graph.add_node("monitor_claim", monitor_claim_node)
    graph.add_node("end_rejected", end_rejected_node)
    graph.add_node("end_review", end_review_node)
    graph.add_node("end_error", end_error_node)

    graph.set_entry_point("extract")
    graph.add_conditional_edges("extract", after_extract, {"price": "price", "end_error": "end_error"})
    graph.add_edge("price", "underwrite")
    graph.add_conditional_edges(
        "underwrite",
        should_issue,
        {"criteria": "criteria", "end_rejected": "end_rejected", "end_review": "end_review"},
    )
    graph.add_conditional_edges(
        "criteria",
        after_criteria,
        {
            "issue": "issue",
            "audit": "audit",
            "end_rejected": "end_rejected",
            "end_review": "end_review",
        },
    )
    graph.add_conditional_edges("audit", after_audit, {"issue": "issue", "end_rejected": "end_rejected"})
    graph.add_edge("issue", "monitor_claim")
    graph.add_edge("monitor_claim", END)
    graph.add_edge("end_rejected", END)
    graph.add_edge("end_review", END)
    graph.add_edge("end_error", END)
    return graph.compile()


def run_flow(
    booking: dict[str, Any] | None = None,
    mode: str = "backtest",
    *,
    mailbox=None,
    document_extractor=None,
    booking_extractor=None,
    artifact_dir=None,
    require_human_confirmation: bool = False,
    audit_gate: bool = False,
    ledger=None,
) -> GraphState:
    app = build_graph(mailbox, document_extractor, booking_extractor, artifact_dir)
    state: dict[str, Any] = {
        "mode": mode,
        "step_log": [],
        "require_human_confirmation": require_human_confirmation,
        "require_audit": audit_gate,
    }
    if booking is not None:
        state["booking"] = booking
    result = app.invoke(state)
    if ledger is not None:
        from governance import regulatory

        ledger.record_state(result)
        regulatory.record(ledger)
    return result
