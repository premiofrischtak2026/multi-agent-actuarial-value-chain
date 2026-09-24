"""Public data sources used by the bootstrap pipeline.

This module is the single place that documents *where* the raw data comes from.
The actual downloading/building lives in ``src/scripts`` (run by data_sync.sync);
keeping the URLs together makes the provenance auditable.
"""

from __future__ import annotations

ANAC_VRA_BASE = "https://siros.anac.gov.br/siros/registros/diversos/vra"
OPENFLIGHTS_AIRPORTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)
OPENFLIGHTS_AIRLINES_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
)
OURAIRPORTS_AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# name -> (url, what it provides, which script consumes it)
SOURCES: dict[str, dict[str, str]] = {
    "anac_vra": {
        "url": ANAC_VRA_BASE,
        "provides": "Cancelamentos e voos domésticos por rota (VRA mensal)",
        "script": "scripts/download_vra.py",
    },
    "openflights": {
        "url": OPENFLIGHTS_AIRPORTS_URL,
        "provides": "Metadados e coordenadas de aeroportos/aerolineas",
        "script": "scripts/download_vra.py",
    },
    "ourairports": {
        "url": OURAIRPORTS_AIRPORTS_URL,
        "provides": "Coordenadas e UF de aeroportos",
        "script": "scripts/build_airports.py",
    },
    "open_meteo": {
        "url": OPEN_METEO_ARCHIVE_URL,
        "provides": "Precipitação diária histórica no destino",
        "script": "scripts/fetch_precipitation.py",
    },
}
