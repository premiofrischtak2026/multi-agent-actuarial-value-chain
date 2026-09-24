"""Named agents of the pipeline (article section 4.8) — roles and restrictions."""

from __future__ import annotations

AGENTS: list[dict[str, str]] = [
    {
        "nome": "Agente Ingestor",
        "papel": "Validação geográfica e normalização de coordenadas",
        "modulo": "ingestion/",
        "restricao": "Só extrai e normaliza; não interpreta risco.",
    },
    {
        "nome": "Agente Avaliador",
        "papel": "Detecta Data Sparsity; se n < 500, sinaliza interpolação",
        "modulo": "pricing/engine.py (sparsity_flag)",
        "restricao": "Só sinaliza; não altera preço.",
    },
    {
        "nome": "Agente Geoprocessor",
        "papel": "Haversine e distância de risco (γ)",
        "modulo": "pricing/geo.py, pricing/network.py",
        "restricao": "Usa coordenadas aprovadas.",
    },
    {
        "nome": "Agente Precificador",
        "papel": "Consolida prêmio via credibilidade e carregamentos",
        "modulo": "pricing/engine.py, pricing/loading.py",
        "restricao": "Só usa a Nota Técnica aprovada.",
    },
    {
        "nome": "Agente Auditor",
        "papel": "Bloqueia θ fora da faixa e viagem contra aviso governamental",
        "modulo": "governance/auditor.py",
        "restricao": "Não calcula preço; só audita.",
    },
]


def describe() -> list[dict[str, str]]:
    return list(AGENTS)
