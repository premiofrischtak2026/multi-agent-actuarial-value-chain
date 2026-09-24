"""Deterministic backtest engine."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backtest.metrics import MetricsAccumulator
from booking_values import accommodation_brl
from config import FIXTURES_DIR
from monitoring.claims import ClaimsEngine
from policy.issuer import PolicyIssuer
from pricing.engine import PriceEngine
from schemas import (
    BacktestMetrics,
    BookingFixture,
    ClaimResult,
    FlowStep,
    PolicyDocument,
    PolicyRecord,
    PricingResult,
    StepEvent,
    UnderwritingDecision,
    UnderwritingResult,
)
from underwriting.rules import UnderwritingEngine


EventCallback = Callable[[StepEvent], Any]


class BacktestEngine:
    def __init__(self):
        self.pricing = PriceEngine()
        self.underwriting = UnderwritingEngine()
        self.issuer = PolicyIssuer()
        self.claims = ClaimsEngine()
        self.metrics = MetricsAccumulator()
        self.policy_records: list[PolicyRecord] = []
        self._paused = asyncio.Event()
        self._paused.set()
        self._stop = False
        self.speed_multiplier = 1.0

    def reset(self) -> None:
        self.underwriting.reset()
        self.issuer.reset_counter()
        self.metrics = MetricsAccumulator()
        self.policy_records = []
        self._stop = False
        self._paused.set()

    def load_fixtures(self, path: Path | None = None) -> list[BookingFixture]:
        fixture_path = path or (FIXTURES_DIR / "sample_bookings.json")
        with fixture_path.open(encoding="utf-8") as f:
            data = json.load(f)
        return [BookingFixture.model_validate(item) for item in data]

    def _emit(self, callback: EventCallback | None, event: StepEvent) -> None:
        if callback:
            callback(event)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_policy_record(
        self,
        booking: BookingFixture,
        pricing: PricingResult,
        underwriting: UnderwritingResult,
        policy: PolicyDocument | None = None,
        claim: ClaimResult | None = None,
    ) -> PolicyRecord:
        route = booking.route or f"{booking.origin_icao}→{booking.dest_icao}"
        return PolicyRecord(
            booking_id=booking.booking_id,
            policy_id=policy.policy_id if policy else None,
            decision=underwriting.decision,
            underwriting_reason=underwriting.reason,
            passenger_name=booking.passenger.name,
            passenger_document=booking.passenger.document,
            origin_icao=booking.origin_icao.upper(),
            dest_icao=booking.dest_icao.upper(),
            route=route,
            flight_date=booking.flight_date,
            stay_city=booking.stay.city,
            stay_start=booking.stay.start,
            stay_end=booking.stay.end,
            ticket_value_brl=booking.ticket_value_brl,
            accommodation_value_brl=accommodation_brl(booking),
            excursion_value_brl=booking.excursion_value_brl,
            capital_insured_brl=pricing.capital_insured_brl,
            premium_brl=pricing.premium_brl,
            pure_premium_brl=pricing.pure_premium_brl,
            issued_at=policy.issued_at if policy else None,
            effective_start=policy.effective_start if policy else None,
            effective_end=policy.effective_end if policy else None,
            has_claim=bool(claim and claim.triggered),
            claim_total_brl=claim.total_paid_brl if claim else 0.0,
            claim_cancel_brl=claim.cancel_paid_brl if claim else 0.0,
            claim_rain_brl=claim.rain_paid_brl if claim else 0.0,
            claim_reasons=claim.reasons if claim else [],
            recomendacao=getattr(underwriting, "recomendacao", None).value if getattr(underwriting, "recomendacao", None) else None,
            metodo=pricing.metodo.value,
            sparsity_flag=pricing.sparsity_flag,
            theta=pricing.theta,
            z_credibilidade=pricing.z_credibilidade,
        )

    def _emit_policy_record(
        self,
        callback: EventCallback | None,
        record: PolicyRecord,
    ) -> None:
        self.policy_records.append(record)
        self._emit(
            callback,
            StepEvent(
                step=FlowStep.POLICY_RECORD,
                booking_id=record.booking_id,
                timestamp=self._now_iso(),
                payload=record.model_dump(mode="json"),
            ),
        )

    def process_booking(
        self,
        booking: BookingFixture,
        callback: EventCallback | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"booking_id": booking.booking_id}

        self._emit(
            callback,
            StepEvent(
                step=FlowStep.PURCHASE,
                booking_id=booking.booking_id,
                timestamp=self._now_iso(),
                payload={
                    "route": f"{booking.origin_icao}→{booking.dest_icao}",
                    "date": str(booking.flight_date),
                },
            ),
        )

        pricing = self.pricing.price(booking)
        result["pricing"] = pricing.model_dump()
        self._emit(
            callback,
            StepEvent(
                step=FlowStep.PRICE,
                booking_id=booking.booking_id,
                timestamp=self._now_iso(),
                payload=pricing.model_dump(),
            ),
        )

        uw = self.underwriting.evaluate(booking, pricing)
        result["underwriting"] = uw.model_dump()
        self._emit(
            callback,
            StepEvent(
                step=FlowStep.UNDERWRITE,
                booking_id=booking.booking_id,
                timestamp=self._now_iso(),
                payload=uw.model_dump(),
            ),
        )

        if uw.decision == UnderwritingDecision.REJECTED:
            self.metrics.record_rejected()
            record = self._build_policy_record(booking, pricing, uw)
            self._emit_policy_record(callback, record)
            self._emit(
                callback,
                StepEvent(
                    step=FlowStep.END,
                    booking_id=booking.booking_id,
                    timestamp=self._now_iso(),
                    payload={"status": "rejected", "record": record.model_dump(mode="json")},
                ),
            )
            result["record"] = record.model_dump(mode="json")
            return result

        policy = self.issuer.issue(booking, pricing)
        result["policy"] = policy.model_dump(mode="json")
        self.metrics.record_issued(pricing.premium_brl, pricing.pure_premium_brl)
        self._emit(
            callback,
            StepEvent(
                step=FlowStep.ISSUE,
                booking_id=booking.booking_id,
                timestamp=self._now_iso(),
                payload=policy.model_dump(mode="json"),
            ),
        )

        claim = self.claims.evaluate(policy, booking, pricing.freq_cancel, pricing.freq_rain_10mm)
        result["claim"] = claim.model_dump()
        self.metrics.record_claim(claim.total_paid_brl)
        self._emit(
            callback,
            StepEvent(
                step=FlowStep.MONITOR,
                booking_id=booking.booking_id,
                timestamp=self._now_iso(),
                payload={
                    "monitoring": "weather+cancellation",
                    "outcome": booking.outcome.model_dump() if booking.outcome else None,
                },
            ),
        )
        self._emit(
            callback,
            StepEvent(
                step=FlowStep.CLAIM,
                booking_id=booking.booking_id,
                timestamp=self._now_iso(),
                payload=claim.model_dump(),
            ),
        )
        record = self._build_policy_record(booking, pricing, uw, policy, claim)
        self._emit_policy_record(callback, record)
        self._emit(
            callback,
            StepEvent(
                step=FlowStep.END,
                booking_id=booking.booking_id,
                timestamp=self._now_iso(),
                payload={
                    "status": "completed",
                    "metrics": self.metrics.snapshot().model_dump(),
                    "record": record.model_dump(mode="json"),
                },
            ),
        )
        result["record"] = record.model_dump(mode="json")
        return result

    def _filter_fixtures(
        self,
        fixtures: list[BookingFixture] | None,
        route_filter: str | None,
        year_filter: int | None,
        limit: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[BookingFixture]:
        items = fixtures or self.load_fixtures()
        if route_filter:
            items = [b for b in items if route_filter.upper() in f"{b.origin_icao}→{b.dest_icao}".upper()]
        if year_filter:
            items = [b for b in items if b.flight_date.year == year_filter]
        if date_from:
            items = [b for b in items if b.flight_date >= date_from]
        if date_to:
            items = [b for b in items if b.flight_date <= date_to]
        if limit is not None:
            items = items[:limit]
        return items

    def count_matching(
        self,
        route_filter: str | None = None,
        year_filter: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        fixtures: list[BookingFixture] | None = None,
    ) -> dict[str, int | str]:
        all_items = fixtures or self.load_fixtures()
        dates = [b.flight_date for b in all_items]
        matched = self._filter_fixtures(
            all_items, route_filter, year_filter, limit=None, date_from=date_from, date_to=date_to
        )
        return {
            "total": len(all_items),
            "matching": len(matched),
            "min_date": min(dates).isoformat() if dates else None,
            "max_date": max(dates).isoformat() if dates else None,
        }

    def run(
        self,
        fixtures: list[BookingFixture] | None = None,
        callback: EventCallback | None = None,
        route_filter: str | None = None,
        year_filter: int | None = None,
        limit: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[dict[str, Any]], BacktestMetrics]:
        self.reset()
        items = self._filter_fixtures(
            fixtures, route_filter, year_filter, limit, date_from, date_to
        )

        results = []
        for booking in items:
            results.append(self.process_booking(booking, callback))
        return results, self.metrics.snapshot()

    def iter_events(
        self,
        fixtures: list[BookingFixture] | None = None,
        delay_ms: float = 100,
        route_filter: str | None = None,
        year_filter: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Iterator[StepEvent]:
        events: list[StepEvent] = []

        def collect(e: StepEvent) -> None:
            events.append(e)

        self.run(
            fixtures,
            callback=collect,
            route_filter=route_filter,
            year_filter=year_filter,
            date_from=date_from,
            date_to=date_to,
        )
        for event in events:
            yield event

    async def run_streaming(
        self,
        fixtures: list[BookingFixture] | None = None,
        queue: asyncio.Queue | None = None,
        delay_ms: float = 200,
        route_filter: str | None = None,
        year_filter: int | None = None,
        limit: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> BacktestMetrics:
        self.reset()
        items = self._filter_fixtures(
            fixtures, route_filter, year_filter, limit, date_from, date_to
        )

        for booking in items:
            if self._stop:
                break
            await self._paused.wait()

            events: list[StepEvent] = []

            def collect(e: StepEvent) -> None:
                events.append(e)

            self.process_booking(booking, collect)
            for event in events:
                if queue is not None:
                    await queue.put(event)
                if delay_ms > 0 and self.speed_multiplier > 0:
                    await asyncio.sleep(delay_ms / 1000 / self.speed_multiplier)

        metrics = self.metrics.snapshot()
        if queue is not None:
            await queue.put({"type": "complete", "metrics": metrics.model_dump()})
        return metrics

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    def stop(self) -> None:
        self._stop = True
        self.resume()

    def set_speed(self, multiplier: float) -> None:
        self.speed_multiplier = max(0.0, multiplier)
