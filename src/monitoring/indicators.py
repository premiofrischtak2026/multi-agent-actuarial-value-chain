"""Monitoring indicators (article Table 16)."""

from __future__ import annotations

from statistics import mean
from typing import Any


def _get(record: Any, key: str, default=0):
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _val(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def compute_indicators(records: list[Any], metrics: Any | None = None) -> dict[str, Any]:
    """Aggregate the Table 16 indicators from processed policy records."""
    if not records:
        return {"n": 0}

    accepted = [r for r in records if _val(_get(r, "decision")) == "accepted"]
    rejected = [r for r in records if r not in accepted]

    premiums = [float(_get(r, "premium_brl", 0.0)) for r in accepted]
    pures = [float(_get(r, "pure_premium_brl", 0.0)) for r in accepted]
    claims = [float(_get(r, "claim_total_brl", 0.0)) for r in accepted]
    thetas = [float(_get(r, "theta", 0.0)) for r in accepted if _get(r, "theta", 0) is not None]
    zs = [float(_get(r, "z_credibilidade")) for r in accepted if _get(r, "z_credibilidade") is not None]

    total_premium = sum(premiums)
    total_claims = sum(claims)
    total_pure = sum(pures)
    loss_ratio = total_claims / total_premium if total_premium else 0.0
    combined_ratio = (total_claims + 0.05 * total_premium) / total_premium if total_premium else 0.0

    return {
        "n": len(records),
        "aceitos": len(accepted),
        "recusados": len(rejected),
        "seguir_ressalva": sum(1 for r in records if _val(_get(r, "recomendacao")) == "seguir_ressalva"),
        "revisao_humana": sum(1 for r in records if _val(_get(r, "recomendacao")) == "revisao_humana"),
        "total_premium_brl": round(total_premium, 2),
        "expected_loss_brl": round(total_pure, 2),
        "total_claims_brl": round(total_claims, 2),
        "burning_cost": round(total_claims / total_premium, 4) if total_premium else 0.0,
        "loss_ratio": round(loss_ratio, 4),
        "combined_ratio": round(combined_ratio, 4),
        "premium_vs_pure": round(total_premium / total_pure, 4) if total_pure else 0.0,
        "metodos": {
            "dados_completos": sum(1 for r in records if _val(_get(r, "metodo")) == "dados_completos"),
            "analogia": sum(1 for r in records if _val(_get(r, "metodo")) == "analogia"),
        },
        "qualidade_dados": {
            "pct_esparso": round(sum(1 for r in records if _get(r, "sparsity_flag")) / len(records), 4),
        },
        "theta": {
            "min": round(min(thetas), 4) if thetas else None,
            "max": round(max(thetas), 4) if thetas else None,
            "media": round(mean(thetas), 4) if thetas else None,
        },
        "z_credibilidade_media": round(mean(zs), 4) if zs else None,
        "override": 0,
        "drift": None,
    }
