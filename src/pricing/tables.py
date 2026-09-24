"""Route/month exposure table lookup."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import DEFAULT_ASSUMPTIONS, exposure_csv_path, ActuarialAssumptions

# Source CSV is produced by the statistics pipeline with Portuguese headers.
EXPOSURE_COLUMN_ALIASES = {
    "rota": "route",
    "origin_regiao": "origin_region",
    "dest_regiao": "dest_region",
    "n_voos": "n_flights",
    "n_cancelados": "n_cancelled",
    "n_voos_com_clima": "n_flights_with_weather",
    "n_chuva_extrema_50mm": "n_extreme_rain_50mm",
    "n_sem_clima": "n_without_weather",
    "n_dia_pico_p99": "n_peak_day_p99",
    "freq_cancelamento": "freq_cancellation",
    "freq_chuva_5mm": "freq_rain_5mm",
    "freq_chuva_10mm": "freq_rain_10mm",
    "freq_chuva_20mm": "freq_rain_20mm",
    "pp_chuva5_brl": "pp_rain5_brl",
    "flag_estacao_chuvosa_tipica_destino": "flag_typical_rainy_season_dest",
    "flag_estacao_seca_tipica_destino": "flag_typical_dry_season_dest",
    "flag_periodo_atipico_sugerido": "flag_suggested_atypical_period",
    "flag_quebra_serie_vra_2016_2017": "flag_vra_series_break_2016_2017",
    "flag_covid_periodo": "flag_covid_period",
    "flag_covid_restrito": "flag_covid_restricted",
    "flag_bucket_com_pico_nacional": "flag_bucket_with_national_peak",
}


def normalize_exposure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Portuguese pipeline headers to English names used in this package."""
    return df.rename(columns=EXPOSURE_COLUMN_ALIASES)


def load_exposure_csv(path: Path) -> pd.DataFrame:
    return normalize_exposure_columns(pd.read_csv(path))


class ExposureTable:
    def __init__(
        self,
        csv_path: Path | None = None,
        assumptions: ActuarialAssumptions | None = None,
    ):
        self.assumptions = assumptions or DEFAULT_ASSUMPTIONS
        path = csv_path or exposure_csv_path()
        self._df = load_exposure_csv(path)
        self._index: dict[tuple[str, str, int, int], pd.Series] = {}
        self._build_index()

    def _build_index(self) -> None:
        for _, row in self._df.iterrows():
            key = (
                str(row["origin_icao"]),
                str(row["dest_icao"]),
                int(row["year"]),
                int(row["month"]),
            )
            self._index[key] = row

    def lookup(
        self,
        origin_icao: str,
        dest_icao: str,
        year: int,
        month: int,
    ) -> pd.Series | None:
        return self._index.get((origin_icao.upper(), dest_icao.upper(), year, month))

    def lookup_with_kind(
        self,
        origin_icao: str,
        dest_icao: str,
        year: int,
        month: int,
    ) -> tuple["pd.Series | None", str]:
        """Return (row, kind) where kind is 'exact', 'nearest' or 'none'."""
        row = self.lookup(origin_icao, dest_icao, year, month)
        if row is not None:
            return row, "exact"
        subset = self._df[
            (self._df["origin_icao"] == origin_icao.upper())
            & (self._df["dest_icao"] == dest_icao.upper())
        ]
        if subset.empty:
            return None, "none"
        return subset.sort_values(["year", "month"], ascending=False).iloc[0], "nearest"

    def lookup_or_nearest(
        self,
        origin_icao: str,
        dest_icao: str,
        year: int,
        month: int,
    ) -> pd.Series | None:
        row, _ = self.lookup_with_kind(origin_icao, dest_icao, year, month)
        return row

    @property
    def dataframe(self) -> pd.DataFrame:
        return self._df
