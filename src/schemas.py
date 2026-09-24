"""Pydantic schemas for flow inputs and outputs."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class FlowStep(str, Enum):
    PURCHASE = "purchase"
    PRICE = "price"
    UNDERWRITE = "underwrite"
    CRITERIA = "criteria"
    ISSUE = "issue"
    MONITOR = "monitor"
    CLAIM = "claim"
    POLICY_RECORD = "policy_record"
    END = "end"


class PricingMethod(str, Enum):
    """How the frequencies behind a quote were obtained (Seção 02)."""

    DADOS_COMPLETOS = "dados_completos"
    ANALOGIA = "analogia"


class AcceptanceCode(str, Enum):
    """Verdict of the acceptance criteria (Tabela 11)."""

    A = "A"    # Aceitar
    AC = "AC"  # Aceitar com condições
    RH = "RH"  # Revisão humana
    R = "R"    # Recusar
    SI = "SI"  # Sem informação


class PolicyVersions(BaseModel):
    """Traceable versions attached to every decision."""

    nota_tecnica: str
    regras: str
    fontes: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """A data source / lookup step recorded in a quote (traceability)."""

    tipo: str
    ref: str
    detalhe: str = ""
    url: str | None = None


class CriterionStatus(str, Enum):
    PASS = "pass"
    DENY = "deny"
    REVIEW = "review"
    INFO = "info"
    CONDITIONAL = "conditional"


class CriterionResult(BaseModel):
    codigo: str
    resultado: CriterionStatus
    evidencia: str = ""


class AcceptanceResult(BaseModel):
    politica: str
    checks: list[CriterionResult] = Field(default_factory=list)
    veredito: AcceptanceCode = AcceptanceCode.SI
    justificativa: str = ""
    versao_regras: str = ""
    condicoes: list[str] = Field(default_factory=list)


class Passenger(BaseModel):
    name: str
    document: str


class Consent(BaseModel):
    """Data-handling consent flags captured at ingestion."""

    termos: bool = False
    privacidade: bool = False


class HotelInfo(BaseModel):
    """Contracted hotel stay; feeds the R01/R02 high-season test."""

    cidade: str
    diarias: int = Field(ge=0)
    categoria: str | None = None
    diaria_contratada: float = Field(ge=0)

    @property
    def total_brl(self) -> float:
        return self.diaria_contratada * self.diarias


class Stay(BaseModel):
    city: str
    start: date
    end: date


class BookingInput(BaseModel):
    booking_id: str
    flight_date: date
    origin_icao: str
    dest_icao: str
    ticket_value_brl: float = Field(gt=0)
    accommodation_value_brl: float = Field(ge=0, default=0.0)
    excursion_value_brl: float = Field(ge=0, default=0.0)
    passenger: Passenger
    stay: Stay
    message_id: str | None = None
    consents: Consent | None = None
    hotel: HotelInfo | None = None
    # Acceptance evidence (article section 04). Optional; gathered by the agents.
    voucher_no_nome: bool | None = None
    mediana_comparaveis: float | None = None
    alta_temporada: bool | None = None
    alta_temporada_excepcional: bool | None = None
    evento_conhecido: bool | None = None
    chuva_ja_ocorreu: bool | None = None
    fonte_indice: str | None = None
    indice_cobre_janela: bool | None = None
    fallback_contratado: bool | None = None
    malha_elegivel: bool | None = None
    fraude_comprovada: bool | None = None
    alerta_fraude: bool | None = None
    sancao: bool | None = None
    aviso_governamental: bool | None = None

    @model_validator(mode="after")
    def legacy_excursion_as_accommodation(self) -> BookingInput:
        """Older fixtures stored accommodation under excursion_value_brl."""
        if self.accommodation_value_brl == 0 and self.excursion_value_brl > 0:
            self.accommodation_value_brl = self.excursion_value_brl
        if self.accommodation_value_brl == 0 and self.hotel is not None:
            self.accommodation_value_brl = self.hotel.total_brl
        return self


class BacktestOutcome(BaseModel):
    """Deterministic historical outcome (backtest only)."""

    cancelled: bool = False
    rain_trigger_10mm: bool = False


class BookingFixture(BookingInput):
    """Backtest fixture with optional ground truth."""

    model_config = ConfigDict(populate_by_name=True)

    outcome: BacktestOutcome | None = None
    year: int | None = None
    month: int | None = None
    route: str | None = Field(default=None, validation_alias=AliasChoices("route", "rota"))


class PricingResult(BaseModel):
    capital_insured_brl: float
    freq_cancel: float
    freq_rain_10mm: float
    pure_premium_brl: float
    pure_rate: float
    commercial_rate: float
    premium_brl: float
    safety_margin_brl: float
    route_key: str
    explanation: str = ""
    metodo: PricingMethod = PricingMethod.DADOS_COMPLETOS
    fontes: list[Source] = Field(default_factory=list)
    aviso: str | None = None
    versao_nota_tecnica: str = ""
    sparsity_flag: bool = False
    n_exposicao: int = 0
    z_credibilidade: float | None = None
    theta: float = 0.0
    multiplicador: float = 1.0
    carregamento_incerteza: float = 0.0
    explicabilidade: dict[str, Any] = Field(default_factory=dict)


class UnderwritingDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class UnderwritingRecommendation(str, Enum):
    """Portfolio recommendation (article section 03)."""

    SEGUIR = "seguir"
    SEGUIR_RESSALVA = "seguir_ressalva"
    REVISAO_HUMANA = "revisao_humana"
    RECUSAR = "recusar"


class UnderwritingResult(BaseModel):
    decision: UnderwritingDecision
    reason: str
    route_exposure_brl: float = 0.0
    policies_on_route_month: int = 0
    recomendacao: UnderwritingRecommendation = UnderwritingRecommendation.SEGUIR
    confirmacao_atuario_requerida: bool = False
    carteira: dict[str, float | int | str] = Field(default_factory=dict)
    achados: list[str] = Field(default_factory=list)
    pontos_a_conferir: list[str] = Field(default_factory=list)
    fontes: list[Source] = Field(default_factory=list)


class PolicyDocument(BaseModel):
    policy_id: str
    booking_id: str
    issued_at: datetime
    effective_start: date
    effective_end: date
    capital_insured_brl: float
    premium_brl: float
    origin_icao: str
    dest_icao: str
    passenger_name: str
    status: str = "active"
    indice: str = "precipitacao"
    fonte_meteorologica: str = "Open-Meteo"
    janela: str = ""
    gatilho_mm: float = 10.0
    ppng_brl: float = 0.0
    quadro_378: dict[str, Any] = Field(default_factory=dict)
    veredito: str | None = None
    politica: str | None = None
    condicoes: list[str] = Field(default_factory=list)


class ClaimResult(BaseModel):
    triggered: bool
    cancel_paid_brl: float = 0.0
    rain_paid_brl: float = 0.0
    total_paid_brl: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    trigger: str = "none"  # none | cancellation | rain | both
    sinistro_id: str | None = None
    precip_mm: float | None = None
    status: str = "closed"  # closed | open | liquidado
    psl_brl: float = 0.0
    quadro_376: dict[str, Any] = Field(default_factory=dict)
    quadro_377: dict[str, Any] = Field(default_factory=dict)


class PolicyRecord(BaseModel):
    """Consolidated summary of each booking processed in the backtest."""

    model_config = ConfigDict(populate_by_name=True)

    booking_id: str
    policy_id: str | None = None
    decision: UnderwritingDecision
    underwriting_reason: str = ""
    passenger_name: str
    passenger_document: str
    origin_icao: str
    dest_icao: str
    route: str = Field(validation_alias=AliasChoices("route", "rota"))
    flight_date: date
    stay_city: str
    stay_start: date
    stay_end: date
    ticket_value_brl: float
    accommodation_value_brl: float = 0.0
    excursion_value_brl: float = 0.0
    capital_insured_brl: float
    premium_brl: float
    pure_premium_brl: float = 0.0
    issued_at: datetime | None = None
    effective_start: date | None = None
    effective_end: date | None = None
    has_claim: bool = False
    claim_total_brl: float = 0.0
    claim_cancel_brl: float = 0.0
    claim_rain_brl: float = 0.0
    claim_reasons: list[str] = Field(default_factory=list)
    recomendacao: str | None = None
    metodo: str | None = None
    sparsity_flag: bool = False
    theta: float = 0.0
    z_credibilidade: float | None = None


class StepEvent(BaseModel):
    """Event emitted during backtest / graph execution."""

    step: FlowStep
    booking_id: str
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)


class BacktestMetrics(BaseModel):
    policies_issued: int = 0
    policies_rejected: int = 0
    total_premium_brl: float = 0.0
    total_claims_brl: float = 0.0
    claims_with_payout: int = 0
    claims_without_payout: int = 0
    loss_ratio: float = 0.0
    combined_ratio: float = 0.0
    expected_pure_premium_brl: float = 0.0
    premium_vs_pure_ratio: float = 0.0
