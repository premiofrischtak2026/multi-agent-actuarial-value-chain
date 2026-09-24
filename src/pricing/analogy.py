"""Analogy quote (article section 02, "método: analogia").

When a route/month/destination lacks mass, the analogy path estimates the
frequencies from regional/comparable data and public sources. The premium is
still produced by the deterministic pricing engine (PriceEngine.price_from_rates);
the agent only selects queries and interprets the answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from booking_values import capital_insured_brl, trip_loss_brl
from config import TECH_NOTE_VERSION
from pricing.engine import PriceEngine
from pricing.geo import AirportTable
from pricing.tables import ExposureTable
from pricing.tools import estatistica_uf_regiao_mes, metadado_aeroporto, premissas_nota_tecnica
from schemas import BookingInput, PricingMethod, PricingResult, Source

DIVERGENCE_THRESHOLD = 0.20


@dataclass
class AnalogyEstimate:
    freq_cancel: float
    freq_rain: float
    fontes: list[Source] = field(default_factory=list)
    consultas: list[str] = field(default_factory=list)
    mediana_regional_chuva: float | None = None
    rotas: list[str] = field(default_factory=list)


def regional_estimate(
    booking: BookingInput,
    table: ExposureTable,
    airport_table: AirportTable,
) -> AnalogyEstimate:
    month = booking.flight_date.month
    route = f"{booking.origin_icao.upper()}→{booking.dest_icao.upper()}"
    dest = metadado_aeroporto(booking.dest_icao, airport_table)
    fontes: list[Source] = [Source(tipo="nota_tecnica", ref=TECH_NOTE_VERSION)]
    consultas = ["premissas_nota_tecnica", "estatistica_uf_regiao_mes"]

    uf = dest["uf"] if dest else None
    regiao = dest["regiao"] if dest else None
    stats_uf = estatistica_uf_regiao_mes(table, month, uf=uf, exclude_route=route)
    stats_reg = estatistica_uf_regiao_mes(table, month, regiao=regiao, exclude_route=route)

    freq_cancel = stats_uf["freq_cancelamento_mediana"]
    freq_rain = stats_uf["freq_chuva_10mm_mediana"]
    if freq_cancel is None:
        freq_cancel = stats_reg["freq_cancelamento_mediana"]
    if freq_rain is None:
        freq_rain = stats_reg["freq_chuva_10mm_mediana"]

    if dest:
        fontes.append(
            Source(tipo="aeroporto", ref=dest["icao"], detalhe=f"{dest['cidade']}/{dest['uf']} · {dest['regiao']}")
        )
    fontes.append(
        Source(tipo="uf_regiao", ref=f"{uf or regiao or 'BR'} {month:02d}", detalhe=f"n={stats_uf['n_celulas']}")
    )
    if freq_cancel is None:
        freq_cancel = PriceEngine.DEFAULT_FREQ_CANCEL
    if freq_rain is None:
        freq_rain = PriceEngine.DEFAULT_FREQ_RAIN

    return AnalogyEstimate(
        freq_cancel=freq_cancel,
        freq_rain=freq_rain,
        fontes=fontes,
        consultas=consultas,
        mediana_regional_chuva=stats_reg["freq_chuva_10mm_mediana"],
    )


def analogy_quote(
    booking: BookingInput,
    table: ExposureTable,
    airport_table: AirportTable,
    *,
    engine: PriceEngine | None = None,
    estimate: AnalogyEstimate | None = None,
) -> PricingResult:
    engine = engine or PriceEngine(table=table, airport_table=airport_table)
    estimate = estimate or regional_estimate(booking, table, airport_table)
    capital = capital_insured_brl(booking)
    loss = trip_loss_brl(booking)

    base = engine.price_from_rates(capital, estimate.freq_cancel, estimate.freq_rain, loss)
    aviso = "Cotação por analogia: frequências estimadas a partir de UF/região e rotas comparáveis."
    if estimate.mediana_regional_chuva:
        base_value = max(estimate.mediana_regional_chuva, 0.01)
        if abs(estimate.freq_rain - estimate.mediana_regional_chuva) / base_value > DIVERGENCE_THRESHOLD:
            aviso += " A frequência de chuva diverge da mediana regional em mais de 20%; segue para conferência."

    fontes = list(estimate.fontes)
    if estimate.consultas:
        fontes.append(Source(tipo="consultas", ref="agente_analogia", detalhe=", ".join(estimate.consultas)))

    return base.model_copy(
        update={
            "metodo": PricingMethod.ANALOGIA,
            "fontes": fontes,
            "aviso": aviso,
            "versao_nota_tecnica": TECH_NOTE_VERSION,
            "route_key": f"{booking.origin_icao.upper()}→{booking.dest_icao.upper()}",
        }
    )
