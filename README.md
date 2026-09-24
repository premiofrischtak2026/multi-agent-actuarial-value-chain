# Fluxo Vertical Agents — Cadeia de Valor Atuarial

Sistema multiagente para a cadeia de valor atuarial de um seguro paramétrico de viagem.

## Quickstart

```bash
uv sync
cd src
make data     # baixa das fontes públicas e reconstrói os dados
make test     # uv run pytest
make start    # API (:8000) + dashboard Vite (:5173)
```

LLM é opcional e configurado via `.env` (veja `.env.example`); sem ele o fluxo é determinístico.

## Estrutura

Código em [`src/`](src): ingestão, motor atuarial (GLM/Haversine/IDW/credibilidade),
subscrição, critérios (R01–R08), emissão, monitoramento/liquidação, governança e
explicabilidade. Ver [`src/README.md`](src/README.md).
