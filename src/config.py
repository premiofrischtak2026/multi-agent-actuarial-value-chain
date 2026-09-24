"""Actuarial assumptions and package configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
SCRIPTS_DIR = PACKAGE_DIR / "scripts"
RAW_DIR = DATA_DIR / "raw"
WORK_DIR = DATA_DIR / "work"
CACHE_DIR = DATA_DIR / "cache_open_meteo"
EXPOSURE_CSV = DATA_DIR / "07_Exposicao_Rota_Mes.csv"
EXPOSURE_GOLDEN_CSV = DATA_DIR / "golden" / "exposure_golden_sample.csv"
EXPOSURE_PARQUET = DATA_DIR / "route_month_exposure.parquet"
FLIGHTS_HISTORY_PARQUET = DATA_DIR / "flights_history_full.parquet"
PRECIPITATION_HISTORY_PARQUET = DATA_DIR / "precipitation_history_full.parquet"
AIRPORTS_CSV = DATA_DIR / "airports.csv"
AIRPORT_PROFILE_CSV = DATA_DIR / "airport_profile.csv"
STORAGE_DIR = DATA_DIR / "storage"
MODELS_DIR = DATA_DIR / "models"
FIXTURES_DIR = PACKAGE_DIR / "fixtures" / "backtest"

# Version stamps attached to decisions and quotes for auditability.
TECH_NOTE_VERSION = "NTA-001@v1.0"
RULES_VERSION = "AC-001@v1.0"


def exposure_csv_path() -> Path:
    """Full exposure table when present, otherwise the committed golden sample."""
    if EXPOSURE_CSV.exists():
        return EXPOSURE_CSV
    if EXPOSURE_GOLDEN_CSV.exists():
        return EXPOSURE_GOLDEN_CSV
    return EXPOSURE_CSV


@dataclass(frozen=True)
class ActuarialAssumptions:
    """Parameters from Actuarial Technical Note No. 001 / scenario workbook."""

    benefit_cancel_brl: float = 500.0  # historical reference from the statistics pipeline
    benefit_rain_brl: float = 300.0  # historical reference from the statistics pipeline
    rain_threshold_mm: float = 10.0
    safety_margin: float = 0.10  # θ = 10%
    theta_min: float = 0.03
    theta_max: float = 0.12
    commission: float = 0.15
    profit: float = 0.03
    administrative_expense: float = 0.05
    k_credibilidade: float = 475.0
    exposicao_plena: float = 500.0
    multiplicador_min: float = 0.80
    multiplicador_max: float = 1.50
    max_capital_insured_brl: float = 15_000.0
    min_capital_insured_brl: float = 100.0
    max_premium_per_route_month_brl: float = 500_000.0
    max_policies_per_route_month: int = 500
    max_capital_per_event_brl: float = 500_000.0
    max_capital_per_region_event_brl: float = 1_000_000.0
    proximity_to_cap: float = 0.80
    # Cap: commercial premium ≤ max_premium_to_cs_ratio × capital insured (e.g. 50%)
    max_premium_to_cs_ratio: float = 0.50
    # Underwriting: reject if freq_cancel + freq_rain_10mm exceeds this limit
    max_combined_event_frequency: float = 0.50


DEFAULT_ASSUMPTIONS = ActuarialAssumptions()

# Reference case — Annex I of the technical note
ANNEX_I_REFERENCE = {
    "pure_rate": 0.00279,
    "capital_insured": 5000.0,
    "commercial_rate": 0.0039857,
    "premium_brl": 19.93,
}
