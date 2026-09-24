"""Deterministic issuance of a parametric policy."""

from __future__ import annotations

from datetime import datetime, timezone

from schemas import BookingInput, PolicyDocument, PricingResult


class PolicyIssuer:
    _counter = 0

    def issue(
        self,
        booking: BookingInput,
        pricing: PricingResult,
        issued_at: datetime | None = None,
        *,
        veredito: str | None = None,
        politica: str | None = None,
        condicoes: list[str] | None = None,
    ) -> PolicyDocument:
        PolicyIssuer._counter += 1
        now = issued_at or datetime.now(timezone.utc)
        policy_id = f"POL-{now.strftime('%Y%m%d')}-{PolicyIssuer._counter:06d}"

        return PolicyDocument(
            policy_id=policy_id,
            booking_id=booking.booking_id,
            issued_at=now,
            effective_start=booking.flight_date,
            effective_end=booking.stay.end,
            capital_insured_brl=pricing.capital_insured_brl,
            premium_brl=pricing.premium_brl,
            origin_icao=booking.origin_icao.upper(),
            dest_icao=booking.dest_icao.upper(),
            passenger_name=booking.passenger.name,
            status="active",
            indice="precipitacao",
            fonte_meteorologica=booking.fonte_indice or "Open-Meteo",
            janela=f"{booking.flight_date.isoformat()}/{booking.stay.end.isoformat()}",
            gatilho_mm=10.0,
            ppng_brl=pricing.premium_brl,
            quadro_378={"movimento": "emissao", "premio_brl": pricing.premium_brl},
            veredito=veredito,
            politica=politica,
            condicoes=list(condicoes or []),
        )

    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
