"""Pricing engine — Actuarial Technical Note No. 001."""

from __future__ import annotations

import math
from statistics import pstdev

from booking_values import capital_insured_brl, trip_loss_brl
from config import DEFAULT_ASSUMPTIONS, TECH_NOTE_VERSION, ActuarialAssumptions, exposure_csv_path
from pricing.credibility import credibility, compose
from pricing.geo import AirportTable, default_airport_table
from pricing.interpolation import interpolate_frequency
from pricing.loading import compute_loading, theta_from_spread
from pricing.network import default_gamma, neighborhood
from pricing.tables import ExposureTable
from schemas import BookingInput, PricingMethod, PricingResult, Source

SPARSITY_THRESHOLD = 500
INTERPOLATION_K = 3
SPREAD_REFERENCE = 0.05


def pure_rate(freq_cancel: float, freq_rain: float, capital_insured: float, loss_basis_brl: float) -> float:
    """Pure rate E[X] = PPR / capital insured."""
    if capital_insured <= 0:
        return 0.0
    return pure_premium(freq_cancel, freq_rain, loss_basis_brl) / capital_insured


def pure_premium(freq_cancel: float, freq_rain: float, loss_basis_brl: float) -> float:
    """PPR = (freq_cancel + freq_rain) × trip loss (flight + accommodation)."""
    return (freq_cancel + freq_rain) * loss_basis_brl


def commercial_rate(pure_rate_value: float, assumptions: ActuarialAssumptions | None = None) -> float:
    """Commercial rate TC = E[X] × (1 + θ) / [1 − (c + d + d_a)]."""
    a = assumptions or DEFAULT_ASSUMPTIONS
    loading = 1.0 - (a.commission + a.profit + a.administrative_expense)
    if loading <= 0:
        raise ValueError("Sum of loadings is >= 100%")
    return pure_rate_value * (1.0 + a.safety_margin) / loading


def commercial_premium(
    capital_insured: float,
    freq_cancel: float,
    freq_rain: float,
    loss_basis_brl: float,
    assumptions: ActuarialAssumptions | None = None,
) -> tuple[float, float, float, float, bool]:
    """Return (ppr, pure_rate, commercial_rate, premium_brl, rate_capped)."""
    a = assumptions or DEFAULT_ASSUMPTIONS
    ppr = pure_premium(freq_cancel, freq_rain, loss_basis_brl)
    pr = pure_rate(freq_cancel, freq_rain, capital_insured, loss_basis_brl)
    cr = commercial_rate(pr, a)
    premium = cr * capital_insured
    rate_capped = False
    max_premium = a.max_premium_to_cs_ratio * capital_insured
    if capital_insured > 0 and premium > max_premium:
        premium = max_premium
        cr = premium / capital_insured
        rate_capped = True
    return ppr, pr, cr, premium, rate_capped


class PriceEngine:
    DEFAULT_FREQ_CANCEL = 0.05
    DEFAULT_FREQ_RAIN = 0.15

    def __init__(
        self,
        table: ExposureTable | None = None,
        assumptions: ActuarialAssumptions | None = None,
        *,
        use_interpolation: bool = True,
        k_neighbors: int = INTERPOLATION_K,
        airport_table: AirportTable | None = None,
        gamma_provider=None,
        multiplier_provider=None,
        uncertainty: float = 0.0,
        frequency_model=None,
    ):
        self.table = table or ExposureTable()
        self.assumptions = assumptions or DEFAULT_ASSUMPTIONS
        self.use_interpolation = use_interpolation
        self.k_neighbors = k_neighbors
        self._airport_table = airport_table
        self.gamma_provider = gamma_provider or default_gamma
        self.multiplier_provider = multiplier_provider
        self.uncertainty = uncertainty
        self.frequency_model = frequency_model

    def _airports(self) -> AirportTable | None:
        if self._airport_table is None:
            try:
                self._airport_table = default_airport_table()
            except (FileNotFoundError, OSError):
                return None
        return self._airport_table

    def capital_insured(self, booking: BookingInput) -> float:
        return capital_insured_brl(booking)

    def price(self, booking: BookingInput) -> PricingResult:
        capital = self.capital_insured(booking)
        loss_basis = trip_loss_brl(booking)
        year = booking.flight_date.year
        month = booking.flight_date.month
        route_key = f"{booking.origin_icao.upper()}→{booking.dest_icao.upper()}"
        source_name = exposure_csv_path().name
        fontes: list[Source] = []
        aviso: str | None = None

        row, kind = self.table.lookup_with_kind(booking.origin_icao, booking.dest_icao, year, month)
        n_exposicao = 0
        local_freq: tuple[float, float] | None = None
        anchors = []
        interp = None

        if row is not None:
            cell_cancel = float(row["freq_cancellation"])
            cell_rain = float(row["freq_rain_10mm"])
            if math.isnan(cell_cancel):
                cell_cancel = self.DEFAULT_FREQ_CANCEL
            if math.isnan(cell_rain):
                cell_rain = self.DEFAULT_FREQ_RAIN
            local_freq = (cell_cancel, cell_rain)
            route_key = str(row.get("route", route_key))
            n_exposicao = int(row.get("n_flights", 0) or 0)
            cell = f"{route_key} {int(row['year'])}-{int(row['month']):02d}"
            fontes.append(Source(tipo="exposicao", ref=source_name, detalhe=cell))
            if kind == "nearest":
                aviso = f"Lookup não exato: usando {cell} (célula rota×mês ausente)."
                fontes.append(Source(tipo="fallback", ref="rota-ultimo-ano-mes", detalhe=cell))

        # Interpolation is used for a gap node, or to complement a sparse local cell.
        glm_freq: tuple[float, float] | None = None
        if local_freq is None and self.frequency_model is not None:
            region = ""
            airports = self._airports()
            if airports is not None:
                airport = airports.get(booking.dest_icao)
                region = airport.regiao if airport else ""
            glm_freq = self.frequency_model.predict(month, region)
            fontes.append(
                Source(tipo="glm", ref="models/frequency_glm.json", detalhe=f"mês {month} · região {region or 'n/d'}")
            )
            aviso = "Sem célula; frequência estimada por GLM calibrado."

        needs_interpolation = (
            (local_freq is None and glm_freq is None)
            or (local_freq is not None and n_exposicao < self.assumptions.exposicao_plena)
        )
        if self.use_interpolation and needs_interpolation:
            airports = self._airports()
            if airports is not None:
                anchors = neighborhood(
                    booking.dest_icao,
                    month,
                    table=self.table,
                    airport_table=airports,
                    k=self.k_neighbors,
                    gamma_provider=self.gamma_provider,
                )
                if anchors:
                    interp = interpolate_frequency(anchors)
                    if local_freq is None:
                        n_exposicao = sum(a.n_flights for a in anchors)
                    detalhe = ", ".join(
                        f"{a.icao} d={a.distancia_km}km w={w:.1%}" for a, w in interp.neighbours
                    )
                    fontes.append(Source(tipo="idw", ref="airports.csv", detalhe=detalhe))
                    if local_freq is None:
                        aviso = (
                            f"Exposição local ausente; frequências estimadas por interpolação IDW "
                            f"(K={self.k_neighbors} vizinhos)."
                        )

        # Credibility composition: local experience blended with the interpolation.
        z: float | None = None
        k_cred = self.assumptions.k_credibilidade
        if local_freq is not None and interp is not None and n_exposicao < self.assumptions.exposicao_plena:
            z = credibility(n_exposicao, k_cred, self.assumptions.exposicao_plena)
            freq_cancel = compose(z, local_freq[0], interp.freq_cancel)
            freq_rain = compose(z, local_freq[1], interp.freq_rain)
            fontes.append(
                Source(tipo="credibilidade", ref="Bühlmann-Straub", detalhe=f"Z={z:.2f} n={n_exposicao} K={k_cred:.0f}")
            )
            aviso = f"{aviso or ''} Prêmio composto por credibilidade.".strip()
        elif local_freq is not None:
            freq_cancel, freq_rain = local_freq
            z = credibility(n_exposicao, k_cred, self.assumptions.exposicao_plena) if n_exposicao >= self.assumptions.exposicao_plena else None
        elif interp is not None:
            freq_cancel, freq_rain = interp.freq_cancel, interp.freq_rain
            z = 0.0
        elif glm_freq is not None:
            freq_cancel, freq_rain = glm_freq
            z = 0.0
        else:
            freq_cancel = self.DEFAULT_FREQ_CANCEL
            freq_rain = self.DEFAULT_FREQ_RAIN
            aviso = f"Sem exposição para {route_key}; fallback padrão 5%/15%."
            fontes.append(Source(tipo="fallback", ref="defaults", detalhe="5% cancel / 15% chuva"))

        sparsity_flag = kind == "none" or n_exposicao < SPARSITY_THRESHOLD

        # θ proportional to the interpolation spread (3%–12%), else the NTA default.
        combined = [a.freq_cancel + a.freq_rain for a in anchors] if anchors else []
        if interp is not None and len(combined) >= 2:
            theta = theta_from_spread(
                pstdev(combined),
                theta_min=self.assumptions.theta_min,
                theta_max=self.assumptions.theta_max,
                spread_ref=SPREAD_REFERENCE,
            )
        else:
            theta = self.assumptions.safety_margin

        multiplier = 1.0
        if self.multiplier_provider is not None:
            multiplier = float(self.multiplier_provider(booking, month))
            multiplier = min(self.assumptions.multiplicador_max, max(self.assumptions.multiplicador_min, multiplier))

        ppr = pure_premium(freq_cancel, freq_rain, loss_basis)
        pr = pure_rate(freq_cancel, freq_rain, capital, loss_basis)
        loading = compute_loading(
            ppr,
            capital,
            self.assumptions,
            theta=theta,
            multiplier=multiplier,
            uncertainty=self.uncertainty,
        )
        premium = loading.premium_brl
        rate_capped = loading.capped
        cr = (premium / capital) if capital > 0 else 0.0
        safety_margin_brl = ppr * theta
        cap_note = (
            f"; {self.assumptions.max_premium_to_cs_ratio:.0%} capital-insured cap applied"
            if rate_capped
            else ""
        )

        localidades = (
            [
                {
                    "icao": a.icao,
                    "cidade": a.cidade,
                    "distancia_km": a.distancia_km,
                    "gamma": a.gamma,
                    "frequencia": a.freq_cancel + a.freq_rain,
                    "peso": round(w, 4),
                }
                for a, w in interp.neighbours
            ]
            if interp is not None
            else []
        )
        explicabilidade = {
            "localidades_referencia": localidades,
            "distancia_metodo": "haversine",
            "frequencia": {"cancel": freq_cancel, "rain": freq_rain, "total": freq_cancel + freq_rain},
            "severidade_brl": round(capital, 2),
            "credibilidade": {
                "Z": z,
                "K": k_cred,
                "n": n_exposicao,
                "limiar": self.assumptions.exposicao_plena,
            },
            "carregamentos": {
                "theta": theta,
                "comissao": self.assumptions.commission,
                "lucro": self.assumptions.profit,
                "despesa_administrativa": self.assumptions.administrative_expense,
            },
            "multiplicador": multiplier,
            "carregamento_incerteza": self.uncertainty,
            "decomposicao": {
                "premio_puro_brl": round(ppr, 4),
                "taxa_pura": pr,
                "taxa_comercial": cr,
                "premio_comercial_brl": round(premium, 2),
                "teto_aplicado": rate_capped,
            },
        }

        return PricingResult(
            capital_insured_brl=round(capital, 2),
            freq_cancel=freq_cancel,
            freq_rain_10mm=freq_rain,
            pure_premium_brl=round(ppr, 4),
            pure_rate=pr,
            commercial_rate=cr,
            premium_brl=round(premium, 2),
            safety_margin_brl=round(safety_margin_brl, 4),
            route_key=route_key,
            metodo=PricingMethod.DADOS_COMPLETOS,
            fontes=fontes,
            aviso=aviso,
            versao_nota_tecnica=TECH_NOTE_VERSION,
            sparsity_flag=sparsity_flag,
            n_exposicao=n_exposicao,
            z_credibilidade=z,
            theta=theta,
            multiplicador=multiplier,
            carregamento_incerteza=self.uncertainty,
            explicabilidade=explicabilidade,
            explanation=(
                f"PPR={ppr:.2f} ((cancel {freq_cancel:.2%} + rain {freq_rain:.2%}) × "
                f"loss BRL {loss_basis:.2f}); θ={theta:.2%}; M={multiplier:.2f}; "
                f"CR={cr:.5%}; premium={premium:.2f}{cap_note}"
            ),
        )

    def price_from_rates(
        self,
        capital_insured: float,
        freq_cancel: float,
        freq_rain: float,
        loss_basis_brl: float | None = None,
    ) -> PricingResult:
        loss = loss_basis_brl if loss_basis_brl is not None else capital_insured
        ppr, pr, cr, premium, _ = commercial_premium(
            capital_insured, freq_cancel, freq_rain, loss, self.assumptions
        )
        return PricingResult(
            capital_insured_brl=capital_insured,
            freq_cancel=freq_cancel,
            freq_rain_10mm=freq_rain,
            pure_premium_brl=round(ppr, 4),
            pure_rate=pr,
            commercial_rate=cr,
            premium_brl=round(premium, 2),
            safety_margin_brl=round(ppr * self.assumptions.safety_margin, 4),
            route_key="reference",
            versao_nota_tecnica=TECH_NOTE_VERSION,
            explanation="Direct calculation from rates",
        )
