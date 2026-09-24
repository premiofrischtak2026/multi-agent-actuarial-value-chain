"""Underwriting rules, portfolio accumulation and recommendation (article 03)."""

from __future__ import annotations

from config import DEFAULT_ASSUMPTIONS, ActuarialAssumptions
from pricing.geo import AirportTable
from schemas import (
    BookingInput,
    PricingMethod,
    PricingResult,
    Source,
    UnderwritingDecision,
    UnderwritingRecommendation,
    UnderwritingResult,
)
from underwriting.portfolio import PolicyEntry, Portfolio


class UnderwritingEngine:
    def __init__(
        self,
        assumptions: ActuarialAssumptions | None = None,
        portfolio: Portfolio | None = None,
        airport_table: AirportTable | None = None,
    ):
        self.assumptions = assumptions or DEFAULT_ASSUMPTIONS
        self.portfolio = portfolio or Portfolio()
        self._airport_table = airport_table

    def _airports(self) -> AirportTable | None:
        if self._airport_table is None:
            try:
                self._airport_table = AirportTable()
            except (FileNotFoundError, OSError):
                return None
        return self._airport_table

    def _region(self, booking: BookingInput) -> str:
        airports = self._airports()
        if airports is None:
            return ""
        airport = airports.get(booking.dest_icao)
        return airport.regiao if airport else ""

    def _route(self, booking: BookingInput) -> str:
        return f"{booking.origin_icao.upper()}→{booking.dest_icao.upper()}"

    def _near_cap(self, projected: float, cap: float) -> bool:
        return cap > 0 and projected >= self.assumptions.proximity_to_cap * cap

    def evaluate(
        self,
        booking: BookingInput,
        pricing: PricingResult,
        portfolio: Portfolio | None = None,
    ) -> UnderwritingResult:
        portfolio = portfolio or self.portfolio
        a = self.assumptions
        reasons: list[str] = []
        capital = pricing.capital_insured_brl

        if capital < a.min_capital_insured_brl:
            reasons.append(f"Capital insured below minimum ({a.min_capital_insured_brl:.0f})")
        if capital > a.max_capital_insured_brl:
            reasons.append(f"Capital insured above maximum ({a.max_capital_insured_brl:.0f})")

        route = self._route(booking)
        year, month = booking.flight_date.year, booking.flight_date.month
        prior_premium, prior_count = portfolio.route_month(route, year, month)
        projected_exposure = prior_premium + pricing.premium_brl
        projected_count = prior_count + 1

        municipio = booking.stay.city
        region = self._region(booking)
        event_capital = portfolio.capital_in_event(municipio, booking.flight_date, booking.stay.end) + capital
        regional_capital = (
            portfolio.capital_in_regional_event(region, booking.flight_date, booking.stay.end) + capital
        )

        if projected_exposure > a.max_premium_per_route_month_brl:
            reasons.append(
                f"Premium exposure on route/month exceeds limit ({projected_exposure:.0f} > {a.max_premium_per_route_month_brl:.0f})"
            )
        if projected_count > a.max_policies_per_route_month:
            reasons.append(f"Number of policies on route/month exceeds limit ({projected_count})")
        if event_capital > a.max_capital_per_event_brl:
            reasons.append(
                f"Event capital exceeds limit ({event_capital:.0f} > {a.max_capital_per_event_brl:.0f})"
            )
        if regional_capital > a.max_capital_per_region_event_brl:
            reasons.append(
                f"Regional event capital exceeds limit ({regional_capital:.0f} > {a.max_capital_per_region_event_brl:.0f})"
            )
        if pricing.pure_rate <= 0:
            reasons.append("Invalid pure rate")

        combined_freq = pricing.freq_cancel + pricing.freq_rain_10mm
        if combined_freq > a.max_combined_event_frequency:
            reasons.append(
                f"Sum of frequencies ({combined_freq:.1%}) exceeds limit of {a.max_combined_event_frequency:.0%}"
            )

        near = (
            self._near_cap(projected_exposure, a.max_premium_per_route_month_brl)
            or self._near_cap(projected_count, a.max_policies_per_route_month)
            or self._near_cap(event_capital, a.max_capital_per_event_brl)
            or self._near_cap(regional_capital, a.max_capital_per_region_event_brl)
        )

        achados: list[str] = []
        pontos: list[str] = []
        if pricing.metodo == PricingMethod.ANALOGIA:
            pontos.append("Cotação por analogia: conferir se a cesta representa o destino no mês.")
        if pricing.aviso:
            achados.append(pricing.aviso)
        if near:
            pontos.append("Exposição próxima de um teto de apetite.")
        if region and self._near_cap(regional_capital, a.max_capital_per_region_event_brl):
            achados.append(f"Concentração regional ({region}): capital no evento {regional_capital:.0f}.")

        if reasons:
            recomendacao = UnderwritingRecommendation.RECUSAR
            decision = UnderwritingDecision.REJECTED
            confirm = False
        elif near:
            recomendacao = UnderwritingRecommendation.REVISAO_HUMANA
            decision = UnderwritingDecision.ACCEPTED
            confirm = True
        elif pricing.metodo == PricingMethod.ANALOGIA or pricing.aviso:
            recomendacao = UnderwritingRecommendation.SEGUIR_RESSALVA
            decision = UnderwritingDecision.ACCEPTED
            confirm = True
        else:
            recomendacao = UnderwritingRecommendation.SEGUIR
            decision = UnderwritingDecision.ACCEPTED
            confirm = False

        if decision == UnderwritingDecision.ACCEPTED:
            portfolio.add(
                PolicyEntry(
                    policy_id=None,
                    booking_id=booking.booking_id,
                    route=route,
                    origin_icao=booking.origin_icao.upper(),
                    dest_icao=booking.dest_icao.upper(),
                    municipio=municipio,
                    start=booking.flight_date,
                    end=booking.stay.end,
                    capital_insured_brl=capital,
                    premium_brl=pricing.premium_brl,
                    region=region,
                )
            )

        carteira = {
            "rota_mes": f"{route}|{year}-{month:02d}",
            "premio_brl": round(projected_exposure, 2),
            "teto_premio_brl": a.max_premium_per_route_month_brl,
            "percentual_teto_premio": round(a.max_premium_per_route_month_brl and projected_exposure / a.max_premium_per_route_month_brl or 0.0, 4),
            "apolices": projected_count,
            "teto_apolices": a.max_policies_per_route_month,
            "capital_evento_brl": round(event_capital, 2),
            "teto_evento_brl": a.max_capital_per_event_brl,
            "regiao": region,
            "capital_regiao_evento_brl": round(regional_capital, 2),
            "teto_regiao_evento_brl": a.max_capital_per_region_event_brl,
        }

        return UnderwritingResult(
            decision=decision,
            recomendacao=recomendacao,
            confirmacao_atuario_requerida=confirm,
            reason="; ".join(reasons) if reasons else "Risk within exposure limits",
            route_exposure_brl=round(prior_premium, 2),
            policies_on_route_month=prior_count,
            carteira=carteira,
            achados=achados,
            pontos_a_conferir=pontos,
            fontes=[Source(tipo="carteira", ref="portfolio")] + list(pricing.fontes),
        )

    def reset(self) -> None:
        self.portfolio = Portfolio()
