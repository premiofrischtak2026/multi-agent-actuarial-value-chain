"""Isolated acceptance criteria (article section 04, R01–R08).

Each function answers pass/deny/review/info with a short piece of evidence.
Kept in one module but strictly isolated per rule so a single rule change does
not mix different fundamentals.
"""

from __future__ import annotations

from config import DEFAULT_ASSUMPTIONS
from criteria.base import AcceptanceContext, condition, deny, info, pass_, review
from schemas import BookingInput, CriterionResult

HOTEL_HIGH_SEASON_LIMIT = 1.30
HOTEL_ABSOLUTE_CAP_BRL = 3_000.0


def consent_and_identity(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    consents = booking.consents
    if consents is None or not (consents.termos and consents.privacidade):
        return deny("consentimento", "Termos/privacidade ausentes")
    if not booking.passenger.document.strip():
        return deny("consentimento", "Documento identificável ausente")
    return pass_("consentimento", "Termos, privacidade e documento presentes")


def future_risk_r06(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    if booking.stay.end < context.reference_date:
        return deny("R06_risco_futuro", "Vigência no passado")
    if booking.evento_conhecido:
        return deny("R06_risco_futuro", "Evento já conhecido na contratação")
    if booking.chuva_ja_ocorreu:
        return deny("R06_risco_futuro", "Chuva já ocorreu no destino")
    return pass_("R06_risco_futuro", "Viagem futura, sem evento conhecido")


def legitimate_interest_r07(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    if booking.voucher_no_nome is False:
        return deny("R07_interesse", "Reserva não está no nome do segurado")
    if booking.voucher_no_nome is None:
        return info("R07_interesse", "Vínculo do comprovante não confirmado")
    return pass_("R07_interesse", "E-ticket/voucher no nome do segurado")


def hotel_r01_r02(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    if booking.alta_temporada_excepcional:
        return review("R01_R02_hotel", "Alta temporada excepcional: revisão humana")
    hotel = booking.hotel
    if hotel is None or hotel.diaria_contratada <= 0:
        return info("R01_R02_hotel", "Diária contratada não informada")
    if booking.mediana_comparaveis:
        ratio = hotel.diaria_contratada / booking.mediana_comparaveis
        if ratio > HOTEL_HIGH_SEASON_LIMIT:
            return deny("R01_R02_hotel", f"Diária {ratio:.0%} da mediana (limite 130%)")
        return pass_("R01_R02_hotel", f"Diária {ratio:.0%} da mediana (≤130%)")
    if not booking.alta_temporada and hotel.diaria_contratada > HOTEL_ABSOLUTE_CAP_BRL:
        return deny("R01_R02_hotel", "Diária acima de R$ 3.000 sem alta temporada")
    return pass_("R01_R02_hotel", "Diária dentro do referencial")


def airline_r03(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    if booking.malha_elegivel is False:
        return deny("R03_malha", "Trecho incompatível com a malha da política")
    if booking.malha_elegivel is None:
        return info("R03_malha", "Elegibilidade da malha não confirmada")
    return pass_("R03_malha", "Voo comercial elegível")


def weather_index(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    if not booking.fonte_indice:
        return info("indice_meteorologico", "Sem fonte de índice confiável")
    if booking.indice_cobre_janela is False and not booking.fallback_contratado:
        return deny("indice_meteorologico", "Fonte não cobre ponto/janela e sem fallback")
    if booking.indice_cobre_janela is False:
        return condition(
            "indice_meteorologico",
            f"Fonte {booking.fonte_indice} não cobre ponto/janela: emitir com fallback contratado",
        )
    return pass_("indice_meteorologico", f"Fonte {booking.fonte_indice} cobre ponto/janela")


def accumulation(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    portfolio = context.portfolio
    if portfolio is None:
        return info("acumulo", "Acúmulo não verificado no instante da emissão")
    municipal = booking.stay.city
    event_capital = portfolio.capital_in_event(municipal, booking.flight_date, booking.stay.end)
    cap = DEFAULT_ASSUMPTIONS.max_capital_per_event_brl
    if event_capital + booking.ticket_value_brl > cap:
        return deny("acumulo", f"Capital no evento excede teto ({event_capital:.0f} > {cap:.0f})")
    return pass_("acumulo", f"Capital no evento {event_capital:.0f} dentro do teto")


def fraud_and_sanctions_r08(booking: BookingInput, context: AcceptanceContext) -> CriterionResult:
    if booking.sancao:
        return deny("R08_fraude_sancoes", "Segurado em lista de sanções (vedação)")
    if booking.fraude_comprovada:
        return deny("R08_fraude_sancoes", "Fraude comprovada")
    if booking.alerta_fraude:
        return pass_("R08_fraude_sancoes", "Alerta isolado de fraude (não recusa sem comprovação)")
    return pass_("R08_fraude_sancoes", "Sem comprovação de fraude, sem vedação")


CHECKS = (
    consent_and_identity,
    future_risk_r06,
    legitimate_interest_r07,
    hotel_r01_r02,
    airline_r03,
    weather_index,
    accumulation,
    fraud_and_sanctions_r08,
)
