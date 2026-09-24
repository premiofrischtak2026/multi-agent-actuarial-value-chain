"""Shared LangGraph state."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

from schemas import (
    AcceptanceResult,
    BookingFixture,
    ClaimResult,
    PolicyDocument,
    PricingResult,
    UnderwritingResult,
)


class GraphState(TypedDict, total=False):
    mode: Literal["backtest", "manual"]
    booking: dict[str, Any]
    booking_model: BookingFixture | None
    pricing: PricingResult | None
    underwriting: UnderwritingResult | None
    acceptance: AcceptanceResult | None
    policy: PolicyDocument | None
    claim: ClaimResult | None
    audit: Any
    messages: Annotated[list, add_messages]
    error: str | None
    missing_fields: list[str]
    require_human_confirmation: bool
    require_audit: bool
    step_log: list[dict[str, Any]]
