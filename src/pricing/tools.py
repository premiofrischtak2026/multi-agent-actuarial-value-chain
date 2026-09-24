"""Analogy toolkit (article Table 9).

Plain functions returning dicts, so an LLM can select and interpret them while
the premium is always produced by the deterministic pricing engine.
"""

from __future__ import annotations

from statistics import median

from config import DEFAULT_ASSUMPTIONS
from pricing.geo import AirportTable
from pricing.tables import ExposureTable


def premissas_nota_tecnica() -> dict:
    a = DEFAULT_ASSUMPTIONS
    return {
        "theta": a.safety_margin,
        "theta_min": a.theta_min,
        "theta_max": a.theta_max,
        "comissao": a.commission,
        "lucro": a.profit,
        "despesa_administrativa": a.administrative_expense,
        "teto_premio_sobre_capital": a.max_premium_to_cs_ratio,
        "capital_minimo": a.min_capital_insured_brl,
        "capital_maximo": a.max_capital_insured_brl,
    }


def metadado_aeroporto(icao: str, airport_table: AirportTable) -> dict | None:
    airport = airport_table.get(icao)
    if airport is None:
        return None
    return {
        "icao": airport.icao,
        "cidade": airport.cidade,
        "uf": airport.uf,
        "regiao": airport.regiao,
        "lat": airport.lat,
        "lon": airport.lon,
    }


def estatistica_uf_regiao_mes(
    table: ExposureTable,
    month: int,
    *,
    uf: str | None = None,
    regiao: str | None = None,
    exclude_route: str | None = None,
) -> dict:
    """Median cancellation/rain frequencies for cells of a UF/region in a month."""
    df = table.dataframe
    cells = df[(df["month"] == month)]
    if regiao:
        cells = cells[cells["dest_region"] == regiao] if "dest_region" in cells.columns else cells
    if uf and "dest_uf" in cells.columns:
        cells = cells[cells["dest_uf"] == uf]
    if exclude_route and "route" in cells.columns:
        cells = cells[cells["route"] != exclude_route]
    cancel = [float(v) for v in cells.get("freq_cancellation", []) if v == v]
    rain = [float(v) for v in cells.get("freq_rain_10mm", []) if v == v]
    return {
        "n_celulas": int(len(cells)),
        "freq_cancelamento_mediana": median(cancel) if cancel else None,
        "freq_chuva_10mm_mediana": median(rain) if rain else None,
    }


def rotas_analogas(
    table: ExposureTable,
    origin_icao: str,
    month: int,
    *,
    min_volume: int = 30,
    limit: int = 5,
) -> list[dict]:
    """Other destinations from the same origin with enough volume in the month."""
    df = table.dataframe
    cells = df[
        (df["month"] == month)
        & (df["origin_icao"] == origin_icao.upper())
        & (df["n_flights"] >= min_volume)
    ]
    if "route" in cells.columns and "dest_icao" in cells.columns:
        cells = cells[~cells["dest_icao"].astype(str).str.upper().eq("")]
    rows = cells.sort_values("n_flights", ascending=False).head(limit)
    return [
        {
            "rota": str(row.get("route", "")),
            "dest_icao": str(row["dest_icao"]),
            "n_flights": int(row["n_flights"]),
            "freq_cancelamento": float(row["freq_cancellation"]),
            "freq_chuva_10mm": float(row["freq_rain_10mm"]),
        }
        for _, row in rows.iterrows()
    ]


def busca_publica(query: str, max_results: int = 3) -> list[dict]:
    """Optional public web search (ddgs). Returns [] when offline/unavailable."""
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            return [
                {"titulo": r.get("title", ""), "url": r.get("href", ""), "trecho": r.get("body", "")}
                for r in ddgs.text(query, max_results=max_results)
            ]
    except Exception:  # pragma: no cover - network dependent
        return []
