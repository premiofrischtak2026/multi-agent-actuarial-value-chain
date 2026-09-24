#!/usr/bin/env python3
"""Build the route×month exposure table used by pricing (CSV + parquet)."""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from paths import (
    EXPOSURE_CSV,
    EXPOSURE_PARQUET,
    WORK_DIR,
    ensure_dirs,
    year_range,
)

BENEFIT_CANCEL_BRL = 500.0
BENEFIT_RAIN_BRL = 300.0

UF_REGION = {
    "AC": "N", "AM": "N", "AP": "N", "PA": "N", "RO": "N", "RR": "N", "TO": "N",
    "AL": "NE", "BA": "NE", "CE": "NE", "MA": "NE", "PB": "NE", "PE": "NE",
    "PI": "NE", "RN": "NE", "SE": "NE",
    "DF": "CO", "GO": "CO", "MT": "CO", "MS": "CO",
    "ES": "SE", "MG": "SE", "RJ": "SE", "SP": "SE",
    "PR": "S", "RS": "S", "SC": "S",
}

# Typical rainy-season months by IBGE macroregion (flag only — nothing is dropped)
RAINY_SEASON_MONTHS = {
    "N": {1, 2, 3, 4, 5, 11, 12},
    "NE": {1, 2, 3, 4, 5, 6},
    "CO": {10, 11, 12, 1, 2, 3},
    "SE": {10, 11, 12, 1, 2, 3},
    "S": {9, 10, 11, 12, 1, 2, 3},
}


def norm_uf(s):
    if pd.isna(s):
        return pd.NA
    u = str(s).strip().upper()
    if len(u) == 2 and u.isalpha():
        return u
    for part in u.replace(",", " ").split():
        if len(part) == 2 and part.isalpha() and part in UF_REGION:
            return part
    return u if u in UF_REGION else pd.NA


def region_from_uf(uf):
    if pd.isna(uf):
        return pd.NA
    return UF_REGION.get(str(uf), pd.NA)


def typical_rainy_season(region, month) -> bool:
    months = RAINY_SEASON_MONTHS.get(str(region) if pd.notna(region) else "", set())
    try:
        return int(month) in months
    except (TypeError, ValueError):
        return False


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    year_start, year_end = year_range(argv)
    ensure_dirs()
    date_min = f"{year_start}-01-01"
    date_max = f"{year_end}-12-31"

    flights_path = WORK_DIR / f"domestic_flights_{year_start}_{year_end}.parquet"
    precip_path = WORK_DIR / f"precipitation_{year_start}_{year_end}.parquet"
    if not flights_path.exists():
        raise SystemExit(f"Missing {flights_path}. Run build_flights.py first.")
    if not precip_path.exists():
        raise SystemExit(f"Missing {precip_path}. Run fetch_precipitation.py first.")

    print("Loading flights...")
    voos = pd.read_parquet(flights_path)
    voos = voos[(voos["flight_date"] >= date_min) & (voos["flight_date"] <= date_max)].copy()
    print("Loading precipitation...")
    precip = pd.read_parquet(precip_path)
    precip = precip[(precip["date"] >= date_min) & (precip["date"] <= date_max)].copy()

    voos["origin_uf"] = voos["origin_state"].map(norm_uf)
    voos["dest_uf"] = voos["dest_state"].map(norm_uf)
    voos["origin_region"] = voos["origin_uf"].map(region_from_uf)
    voos["dest_region"] = voos["dest_uf"].map(region_from_uf)

    y = voos["year"].astype(int)
    m = voos["month"].astype(int)
    voos["flag_covid_period"] = y.isin([2020, 2021])
    voos["flag_covid_restricted"] = ((y == 2020) & (m >= 3)) | (y == 2021)
    voos["flag_vra_series_break_2016_2017"] = y.isin([2016, 2017])
    voos["flag_suggested_atypical_period"] = (
        voos["flag_vra_series_break_2016_2017"] | voos["flag_covid_period"]
    )
    voos["flag_typical_rainy_season_dest"] = [
        typical_rainy_season(r, mo) for r, mo in zip(voos["dest_region"], voos["month"])
    ]
    voos["flag_typical_dry_season_dest"] = ~voos["flag_typical_rainy_season_dest"]

    p = precip[["dest_icao", "date", "precip_mm"]].rename(columns={"date": "flight_date"})
    mrg = voos.merge(p, on=["dest_icao", "flight_date"], how="left")
    mrg["flag_no_weather"] = mrg["precip_mm"].isna()
    mrg["flag_rain_5mm"] = mrg["precip_mm"].notna() & (mrg["precip_mm"] >= 5)
    mrg["flag_rain_10mm"] = mrg["precip_mm"].notna() & (mrg["precip_mm"] > 10)
    mrg["flag_rain_20mm"] = mrg["precip_mm"].notna() & (mrg["precip_mm"] >= 20)
    mrg["flag_extreme_rain_50mm"] = mrg["precip_mm"].notna() & (mrg["precip_mm"] >= 50)
    mrg["flag_cancel_claim"] = mrg["cancelled"].astype(bool)
    mrg["flag_double_trigger_5mm"] = mrg["flag_cancel_claim"] & mrg["flag_rain_5mm"]

    daily = mrg.groupby("flight_date", as_index=False).agg(
        n_cancel=("cancelled", "sum"), n_flights=("cancelled", "size")
    )
    thr_p99 = daily["n_cancel"].quantile(0.99)
    peak_days = set(daily.loc[daily["n_cancel"] >= thr_p99, "flight_date"].astype(str))
    mrg["flag_national_cancel_peak_p99"] = mrg["flight_date"].astype(str).isin(peak_days)

    mrg["route"] = mrg["origin_icao"].astype(str) + "→" + mrg["dest_icao"].astype(str)
    g = (
        mrg.groupby(
            [
                "year",
                "month",
                "route",
                "origin_icao",
                "origin_city",
                "origin_uf",
                "origin_region",
                "dest_icao",
                "dest_city",
                "dest_uf",
                "dest_region",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            n_flights=("cancelled", "size"),
            n_cancelled=("cancelled", "sum"),
            n_flights_with_weather=("precip_mm", lambda s: int(s.notna().sum())),
            n_trigger_5mm=("flag_rain_5mm", "sum"),
            n_trigger_10mm=("flag_rain_10mm", "sum"),
            n_trigger_20mm=("flag_rain_20mm", "sum"),
            n_extreme_rain_50mm=("flag_extreme_rain_50mm", "sum"),
            n_double_5mm=("flag_double_trigger_5mm", "sum"),
            n_without_weather=("flag_no_weather", "sum"),
            n_peak_day_p99=("flag_national_cancel_peak_p99", "sum"),
        )
        .sort_values(["year", "month", "n_flights"], ascending=[True, True, False])
    )

    g["flag_covid_period"] = g["year"].astype(int).isin([2020, 2021])
    g["flag_covid_restricted"] = (
        ((g["year"].astype(int) == 2020) & (g["month"].astype(int) >= 3))
        | (g["year"].astype(int) == 2021)
    )
    g["flag_vra_series_break_2016_2017"] = g["year"].astype(int).isin([2016, 2017])
    g["flag_suggested_atypical_period"] = (
        g["flag_vra_series_break_2016_2017"] | g["flag_covid_period"]
    )
    g["flag_typical_rainy_season_dest"] = [
        typical_rainy_season(r, mo) for r, mo in zip(g["dest_region"], g["month"])
    ]
    g["flag_typical_dry_season_dest"] = ~g["flag_typical_rainy_season_dest"]
    g["flag_bucket_with_national_peak"] = (g["n_peak_day_p99"] / g["n_flights"]) >= 0.5

    g["freq_cancellation"] = g["n_cancelled"] / g["n_flights"]
    g["freq_rain_5mm"] = np.where(
        g["n_flights_with_weather"] > 0, g["n_trigger_5mm"] / g["n_flights_with_weather"], np.nan
    )
    g["freq_rain_10mm"] = np.where(
        g["n_flights_with_weather"] > 0, g["n_trigger_10mm"] / g["n_flights_with_weather"], np.nan
    )
    g["freq_rain_20mm"] = np.where(
        g["n_flights_with_weather"] > 0, g["n_trigger_20mm"] / g["n_flights_with_weather"], np.nan
    )
    g["pp_cancel_brl"] = g["freq_cancellation"] * BENEFIT_CANCEL_BRL
    g["pp_rain5_brl"] = g["freq_rain_5mm"] * BENEFIT_RAIN_BRL
    g["pp_total_brl"] = g["pp_cancel_brl"].fillna(0) + g["pp_rain5_brl"].fillna(0)

    flag_cols = [c for c in g.columns if c.startswith("flag_")]
    base_cols = [c for c in g.columns if c not in flag_cols]
    g = g[base_cols + sorted(flag_cols)]

    g.to_csv(EXPOSURE_CSV, index=False, encoding="utf-8-sig")
    g.to_parquet(EXPOSURE_PARQUET, index=False)
    print("Wrote", EXPOSURE_CSV, "rows", len(g))
    print("Wrote", EXPOSURE_PARQUET)


if __name__ == "__main__":
    main()
