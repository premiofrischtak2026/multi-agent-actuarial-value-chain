
<h1 align="center">Fluxo Vertical Agents — Cadeia de Valor Atuarial</h1>

Sistema de agentes para a cadeia de valor atuarial de um **seguro paramétrico de viagem**
(cancelamento de voo e precipitação > 10 mm no destino).
*

## Princípios

| Camada            | Função                                            |
| ----------------- | --------------------------------------------------- | 
| Inferência de IA | extrair, classificar, selecionar consultas, redigir |
| Motor atuarial    | GLM, grafo/IDW, credibilidade, carregamentos        |
| Motor de regras   | elegibilidade, limites, acumulação, impeditivos   |
| Decisão humana   | valida exceções, baixa confiança, extrapolações, corfima aceites  |

## Fluxo

```
e-mail/PDF → extração → cotação → subscrição → critérios → emissão → monitoramento → sinistro
                              (dados completos | analogia | interpolação/credibilidade)
```

Grafo LangGraph (`graph/workflow.py`):
`extract → price → underwrite → criteria → issue → monitor_claim` (e `end_rejected` / `end_review` / `end_error`).

## Dependências e ambiente

Projeto gerenciado com **uv** (sem empacotar como módulo):

```bash
uv sync
```

## Dados

Os arquivos grandes (voos/precipitação/exposição) **não são versionados**. Para baixar das
**fontes públicas** (ANAC VRA, OpenFlights/OurAirports, Open-Meteo) e reconstruir:

```bash
cd src
make data            # = uv run python -m main data sync
# ou, sem rede, usando a amostra "golden" versionada:
uv run python -m main data sync --offline
```

Sem os dados completos, o sistema usa `src/data/golden/exposure_golden_sample.csv`.

## Como rodar

A partir de `src/`:

```bash
make start                       # API (:8000) + dashboard Vite (:5173)
# ou separadamente
uv run python -m main serve      # FastAPI
cd dashboard && npm install && npm run dev
```

CLI:

```bash
uv run python -m main backtest                        # backtest determinístico
uv run python -m main run fixtures/backtest/sample_bookings.json --mode manual
uv run python -m main data sync [--offline|--force]
```

## LLM (multi-provedor)

O modelo/provedor vêm **só do `.env`**, sem default (veja `../.env.example`):

```env
LLM_PROVIDER=openrouter            # openai | openrouter | litellm | <OpenAI-compatível>
LLM_MODEL=anthropic/claude-sonnet-4-6
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=***
```

Sem essas variáveis o caminho com LLM fica desativado e o fluxo segue determinístico.

## Estrutura

```
src/
├── main.py                 # CLI (data, fixtures, backtest, run, serve, demo)
├── config.py               # premissas atuariais, caminhos e versões
├── schemas.py              # modelos Pydantic (contratos)
├── llm.py                  # fábrica de chat model multi-provedor (.env)
├── booking_values.py       # capital segurado / perda
│
├── data_sync/              # bootstrap das fontes públicas (sources, sync)
├── ingestion/              # e-mail/PDF → BookingInput (ports + adapters)
├── pricing/                # engine, tables, geo, network, idw, interpolation,
│                           # credibility, loading, glm, tools, analogy, impact
├── underwriting/           # rules (carteira, recomendação) + portfolio
├── criteria/               # R01–R08 + veredito A/AC/RH/R/SI
├── policy/                 # emissão (PPNG, Quadro 378)
├── monitoring/             # claims (backtest), index_monitor, settlement, indicators
├── storage/                # bases de apólices e sinistros (JSONL)
├── governance/             # ledger, auditor, hitl, agents
├── reporting/              # dossiê de explicabilidade
├── graph/                  # LangGraph (state, workflow)
├── backtest/               # engine, fixtures, metrics, challenger
├── scripts/                # pipeline ANAC/Open-Meteo + builders de dados
├── dashboard/              # React + TypeScript (Vite)
├── data/                   # exposição, históricos, airports.csv, golden sample
├── fixtures/backtest/      # reservas sintéticas + e-mails/PDF de exemplo
└── images/
```

## Funcionalidades

- **Ingestão**: canal de e-mail (IMAP/local/fixture) + extração de PDF; campos faltantes param o fluxo.
- **Cotação**: dados completos (rota×mês) ou **analogia** (UF/região/rotas análogas/busca pública); método e fontes registrados.
- **Motor atuarial**: Haversine + γ + IDW, Bühlmann-Straub (Z=n/(n+K)), θ∈[3%,12%], multiplicador dinâmico e carregamento de incerteza; GLM frequência (Poisson/NB) e severidade (Gamma/Log-Normal).
- **Subscrição**: carteira persistente (rota×mês e capital no evento), recomendação seguir/ressalva/revisão/recusar.
- **Critérios**: R01/R02 hotel, R03 malha, R06 risco futuro, R07 interesse, R08 fraude/sanções, índice, acúmulo → veredito A/AC/RH/R/SI.
- **Emissão**: PPNG=100% e Quadro 378.
- **Monitoramento/liquidação**: chuva estrita > 10,0 mm + cancelamento; Quadros 376/377; PSL→0 e PPNG pro rata die.
- **Governança**: ledger imutável (hash encadeado), Agente Auditor, HITL/override.
- **Explicabilidade**: dossiê por apólice (`reporting/dossier.py`).

## Testes

```bash
make test          # = uv run pytest (a partir da raiz do projeto)
```

## Troubleshooting

- **`make data` sem rede**: use `--offline` (usa a golden sample).
- **Sem dados completos**: rode `make data`; o boot da API apenas avisa.
- **Modo manual sem resposta do LLM**: confira `../.env`
