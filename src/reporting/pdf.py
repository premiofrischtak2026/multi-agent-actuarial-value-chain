"""PDF rendering of the actuarial dossier / quote (article section 6)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# The default PDF fonts are Latin-1; map symbols used in the dossier.
_SYMBOLS = {"γ": "gamma", "θ": "theta", "λ": "lambda", "μ": "mu", "≤": "<=", "≥": ">=", "→": "->"}


def _safe(text: Any) -> str:
    value = str(text)
    for symbol, replacement in _SYMBOLS.items():
        value = value.replace(symbol, replacement)
    return value.encode("latin-1", "replace").decode("latin-1")


def _paragraphs(dossier: dict[str, Any]) -> list:
    styles = getSampleStyleSheet()
    story: list = []
    head = dossier.get("cabecalho", {})

    story.append(Paragraph(_safe(f"Dossie atuarial - {head.get('booking_id', '')}"), styles["Title"]))
    story.append(
        Paragraph(
            _safe(
                f"Rota {head.get('rota')} | Metodo {head.get('metodo')} | Politica {head.get('policy_id')}"
            ),
            styles["Normal"],
        )
    )
    versions = dossier.get("versoes", {})
    story.append(
        Paragraph(
            _safe(f"NTA {versions.get('nota_tecnica')} - regras {versions.get('regras')}"),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Mapa de variaveis", styles["Heading2"]))
    for key, value in dossier.get("mapa_variaveis", {}).items():
        story.append(Paragraph(_safe(f"{key}: {value}"), styles["Normal"]))

    if dossier.get("localidades_referencia"):
        story.append(Paragraph("Localidades de referencia (IDW)", styles["Heading2"]))
        for loc in dossier["localidades_referencia"]:
            story.append(
                Paragraph(
                    _safe(
                        f"{loc['icao']} ({loc['cidade']}) d={loc['distancia_km']}km gamma={loc['gamma']} "
                        f"lambda={loc['frequencia']:.4f} peso={loc['peso']:.1%}"
                    ),
                    styles["Normal"],
                )
            )

    story.append(Paragraph("Decomposicao PP -> PC", styles["Heading2"]))
    for key, value in dossier.get("decomposicao_pp_pc", {}).items():
        story.append(Paragraph(_safe(f"{key}: {value}"), styles["Normal"]))

    story.append(Paragraph("Criterios de aceitacao", styles["Heading2"]))
    criterios = dossier.get("criterios", {})
    story.append(Paragraph(_safe(f"Veredito: {criterios.get('veredito')} - {criterios.get('justificativa')}"), styles["Normal"]))
    for check in criterios.get("checks", []):
        story.append(Paragraph(_safe(f"[{check['resultado']}] {check['codigo']}: {check['evidencia']}"), styles["Normal"]))

    if dossier.get("pendencias"):
        story.append(Paragraph("Pendencias", styles["Heading2"]))
        for item in dossier["pendencias"]:
            story.append(Paragraph(_safe(f"- {item}"), styles["Normal"]))

    if dossier.get("auditoria", {}).get("parecer"):
        story.append(Paragraph("Parecer do Agente Auditor", styles["Heading2"]))
        story.append(Paragraph(_safe(dossier["auditoria"]["parecer"]), styles["Normal"]))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Entregaveis", styles["Heading2"]))
    for item in dossier.get("entregaveis", []):
        story.append(Paragraph(_safe(f"- {item}"), styles["Normal"]))
    return story


def render_dossier_pdf(dossier: dict[str, Any], path: Path | None = None) -> bytes:
    """Render the dossier to PDF bytes; optionally write to ``path``."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title="Dossie atuarial")
    document.build(_paragraphs(dossier))
    data = buffer.getvalue()
    if path is not None:
        Path(path).write_bytes(data)
    return data
