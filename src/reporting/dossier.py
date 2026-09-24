"""Actuarial explainability dossier (article section 6)."""

from __future__ import annotations

from typing import Any

from governance.regulatory import REGULATORY_VERSION, references
from schemas import AcceptanceResult, PolicyDocument, PricingResult, UnderwritingResult


def build_dossier(
    *,
    booking: dict[str, Any],
    pricing: PricingResult,
    underwriting: UnderwritingResult | None = None,
    acceptance: AcceptanceResult | None = None,
    policy: PolicyDocument | None = None,
    audit: Any = None,
) -> dict[str, Any]:
    ex = pricing.explicabilidade or {}
    cred = ex.get("credibilidade", {})

    pendencias: list[str] = []
    if underwriting:
        pendencias.extend(underwriting.pontos_a_conferir)
    if pricing.sparsity_flag:
        pendencias.append("Dados esparsos: revisar quando houver exposição/sinistros locais.")

    dossier: dict[str, Any] = {
        "cabecalho": {
            "booking_id": booking.get("booking_id"),
            "policy_id": policy.policy_id if policy else None,
            "rota": f"{booking.get('origin_icao')}→{booking.get('dest_icao')}",
            "vigencia": pricing.route_key,
            "metodo": pricing.metodo.value,
        },
        "versoes": {
            "nota_tecnica": pricing.versao_nota_tecnica,
            "regras": acceptance.versao_regras if acceptance else None,
            "fontes": [f"{s.tipo}:{s.ref}" for s in pricing.fontes],
        },
        "mapa_variaveis": {
            "capital_segurado_brl": pricing.capital_insured_brl,
            "frequencia_cancelamento": pricing.freq_cancel,
            "frequencia_chuva_10mm": pricing.freq_rain_10mm,
            "severidade_brl": ex.get("severidade_brl", pricing.capital_insured_brl),
            "n_exposicao": pricing.n_exposicao,
        },
        "localidades_referencia": ex.get("localidades_referencia", []),
        "credibilidade": {
            "Z": pricing.z_credibilidade if pricing.z_credibilidade is not None else cred.get("Z"),
            "K": cred.get("K"),
            "n": cred.get("n", pricing.n_exposicao),
            "limiar": cred.get("limiar"),
        },
        "sparsity": {
            "flag": pricing.sparsity_flag,
            "motivo": pricing.aviso,
            "peso_credibilidade": pricing.z_credibilidade,
        },
        "decomposicao_pp_pc": ex.get("decomposicao", {}),
        "carregamentos": ex.get("carregamentos", {}),
        "multiplicador": pricing.multiplicador,
        "criterios": {
            "veredito": acceptance.veredito.value if acceptance else None,
            "justificativa": acceptance.justificativa if acceptance else None,
            "checks": [
                {"codigo": c.codigo, "resultado": c.resultado.value, "evidencia": c.evidencia}
                for c in (acceptance.checks if acceptance else [])
            ],
        },
        "carteira": underwriting.carteira if underwriting else {},
        "pendencias": pendencias,
        "auditoria": {
            "bloqueado": getattr(audit, "bloqueado", None),
            "parecer": getattr(audit, "parecer", None),
        },
        "regulatorio": {
            "versao": REGULATORY_VERSION,
            "provisoes": "Circular SUSEP 648 (PPNG/PSL)",
            "referencias": references(),
        },
        "entregaveis": [
            "PDF da cotação (comprovantes e extração)",
            "Cotação (dados completos ou analogia)",
            "Relatório de carteira",
            "Relatório de critérios",
            "Dossiê de explicabilidade",
        ],
    }
    return dossier


def render_markdown(dossier: dict[str, Any]) -> str:
    lines: list[str] = []
    head = dossier["cabecalho"]
    lines.append(f"# Dossiê atuarial — {head['booking_id']}")
    lines.append(f"- Rota: {head['rota']}  |  Método: {head['metodo']}  |  Política: {head.get('policy_id')}")
    lines.append(f"- Versões: NTA {dossier['versoes']['nota_tecnica']} · regras {dossier['versoes']['regras']}")
    lines.append("")
    lines.append("## Mapa de variáveis")
    for key, value in dossier["mapa_variaveis"].items():
        lines.append(f"- {key}: {value}")
    if dossier["localidades_referencia"]:
        lines.append("")
        lines.append("## Localidades de referência (IDW)")
        for loc in dossier["localidades_referencia"]:
            lines.append(
                f"- {loc['icao']} ({loc['cidade']}) d={loc['distancia_km']}km γ={loc['gamma']} "
                f"λ={loc['frequencia']:.4f} peso={loc['peso']:.1%}"
            )
    lines.append("")
    lines.append("## Decomposição PP → PC")
    for key, value in dossier["decomposicao_pp_pc"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Critérios de aceitação")
    lines.append(f"- Veredito: {dossier['criterios']['veredito']} — {dossier['criterios']['justificativa']}")
    for check in dossier["criterios"]["checks"]:
        lines.append(f"  - [{check['resultado']}] {check['codigo']}: {check['evidencia']}")
    if dossier["pendencias"]:
        lines.append("")
        lines.append("## Pendências")
        for item in dossier["pendencias"]:
            lines.append(f"- {item}")
    if dossier["auditoria"].get("parecer"):
        lines.append("")
        lines.append(f"## Parecer do Agente Auditor\n{dossier['auditoria']['parecer']}")
    return "\n".join(lines)
