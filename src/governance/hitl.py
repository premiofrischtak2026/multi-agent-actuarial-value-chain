"""Human-in-the-Loop: alçadas and override registration (article section 4.8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from governance.ledger import Ledger
from schemas import AcceptanceCode


@dataclass(frozen=True)
class Override:
    actor: str
    motivo: str
    decisao: str
    timestamp: str


def requires_approval(veredito: AcceptanceCode | str) -> bool:
    code = veredito.value if isinstance(veredito, AcceptanceCode) else str(veredito)
    return code in {AcceptanceCode.RH.value, AcceptanceCode.SI.value}


def register_override(
    ledger: Ledger,
    *,
    actor: str,
    motivo: str,
    decisao: str,
) -> Override:
    if not motivo.strip():
        raise ValueError("Override exige motivo")
    override = Override(
        actor=actor,
        motivo=motivo.strip(),
        decisao=decisao,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    ledger.append(actor, "override", {"motivo": override.motivo, "decisao": decisao})
    return override
