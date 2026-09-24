"""Versioned regulatory references (article section 10 / observação).

The article lists methodological and normative sources (Circular SUSEP 648,
IFRS 17, Lei 15.040/2024, SUSEP norms). These are recorded as versioned
references so every decision can point to the applicable framework.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

REGULATORY_VERSION = "REG@v1.0"


@dataclass(frozen=True)
class RegulatoryRef:
    codigo: str
    titulo: str
    versao: str
    ambito: str


REFS: tuple[RegulatoryRef, ...] = (
    RegulatoryRef(
        codigo="CIRCULAR_SUSEP_648",
        titulo="Provisões técnicas (PPNG, PSL)",
        versao="a conferir na revisão jurídica",
        ambito="SUSEP",
    ),
    RegulatoryRef(
        codigo="IFRS17",
        titulo="Contratos de seguro — mensuração e reporte",
        versao="texto e alterações vigentes a conferir",
        ambito="IASB",
    ),
    RegulatoryRef(
        codigo="LEI_15040_2024",
        titulo="Normas de seguro privado",
        versao="vigência e aplicação a conferir",
        ambito="Brasil",
    ),
    RegulatoryRef(
        codigo="SUSEP_REPORTE",
        titulo="Governança, registro e reporte",
        versao="relação específica a completar",
        ambito="SUSEP",
    ),
)


def references() -> list[dict[str, str]]:
    return [asdict(ref) for ref in REFS]


def version() -> str:
    return REGULATORY_VERSION


def record(ledger) -> None:
    """Append the applicable regulatory references to the audit ledger."""
    ledger.append("sistema", "regulatorio", {"versao": REGULATORY_VERSION, "referencias": references()})
