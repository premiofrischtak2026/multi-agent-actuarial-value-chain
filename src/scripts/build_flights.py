#!/usr/bin/env python3
"""Build domestic BR flights parquet from downloaded ANAC VRA CSVs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from paths import (
    AIRLINES_DAT,
    AIRPORTS_DAT,
    FLIGHTS_HISTORY_PARQUET,
    VRA_DIR,
    WORK_DIR,
    ensure_dirs,
    year_range,
)

# ANAC VRA CSV headers (Portuguese source) → English columns
COL_MAP = {
    "Sigla ICAO Empresa Aérea": "carrier_icao",
    "Empresa Aérea": "airline_name",
    "Número Voo": "flight_number_raw",
    "Código DI": "codigo_di",
    "Código Tipo Linha": "tipo_linha",
    "Modelo Equipamento": "aircraft_icao",
    "Número de Assentos": "seats",
    "Sigla ICAO Aeroporto Origem": "origin_icao",
    "Descrição Aeroporto Origem": "origin_desc",
    "Partida Prevista": "dep_sched_raw",
    "Partida Real": "dep_actual_raw",
    "Sigla ICAO Aeroporto Destino": "dest_icao",
    "Descrição Aeroporto Destino": "dest_desc",
    "Chegada Prevista": "arr_sched_raw",
    "Chegada Real": "arr_actual_raw",
    "Situação Voo": "situacao_voo",
    "Justificativa": "justificativa",
    "Referência": "referencia_raw",
    "Situação Partida": "situacao_partida",
    "Situação Chegada": "situacao_chegada",
    "Codeshare": "codeshare",
}


def load_lookups() -> tuple[pd.DataFrame, dict[str, str]]:
    if not AIRPORTS_DAT.exists() or not AIRLINES_DAT.exists():
        raise SystemExit("Missing OpenFlights lookups. Run download_vra.py first.")
    airports = pd.read_csv(
        AIRPORTS_DAT,
        header=None,
        names=[
            "of_id", "name", "city", "country", "iata", "icao", "lat", "lon",
            "alt", "tz_offset", "dst", "timezone", "type", "source",
        ],
        na_values=["\\N", ""],
    )
    airports = airports[airports["icao"].notna() & (airports["icao"].astype(str).str.len() == 4)].copy()
    airports["icao"] = airports["icao"].astype(str).str.upper()
    airports = airports.drop_duplicates("icao", keep="first")
    ap_slim = airports[["icao", "iata", "city", "country", "lat", "lon", "timezone"]].rename(
        columns={"iata": "iata_code", "city": "city_of", "country": "country_of"}
    )

    airlines = pd.read_csv(
        AIRLINES_DAT,
        header=None,
        names=["al_id", "name", "alias", "iata", "icao", "callsign", "country", "active"],
        na_values=["\\N", ""],
    )
    airlines = airlines[airlines["icao"].notna() & (airlines["icao"].astype(str).str.len() == 3)].copy()
    airlines["icao"] = airlines["icao"].astype(str).str.upper()
    airlines["_active"] = (airlines["active"].astype(str).str.upper() == "Y").astype(int)
    airlines = airlines.sort_values(["icao", "_active"], ascending=[True, False]).drop_duplicates(
        "icao", keep="first"
    )
    al_map = airlines.set_index("icao")["iata"].to_dict()
    return ap_slim, al_map


def parse_city_from_desc(desc):
    if pd.isna(desc):
        return pd.NA, pd.NA, pd.NA
    s = str(desc).strip()
    parts = [p.strip() for p in s.split(" - ")]
    country = pd.NA
    state = pd.NA
    city = pd.NA
    if parts:
        last = parts[-1].upper()
        if "BRASIL" in last or last in ("BRAZIL",):
            country = "Brazil"
            if len(parts) >= 3:
                state = parts[-2]
                city = parts[-3]
            elif len(parts) >= 2:
                city = parts[-2]
        else:
            country = parts[-1]
            if len(parts) >= 2:
                city = parts[-2]
    return city, state, country


def parse_dt(series):
    return pd.to_datetime(series, format="mixed", dayfirst=True, errors="coerce")


def map_status(s):
    if pd.isna(s):
        return "UNKNOWN"
    u = str(s).strip().upper()
    if u in ("CANCELADO", "CANCELADA"):
        return "CANCELLED"
    if u in ("REALIZADO", "REALIZADA"):
        return "OPERATED"
    if "NÃO INFORMADO" in u or "NAO INFORMADO" in u:
        return "UNKNOWN"
    return u


def read_csv_robust(path: Path) -> pd.DataFrame:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(path, sep=";", encoding=enc, low_memory=False, dtype=str)
            df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
            return df
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"encoding fail: {path}")


def process_month(path: Path, year: int, ap_slim, al_map) -> pd.DataFrame:
    raw = read_csv_robust(path)
    raw = raw.rename(columns=COL_MAP)
    for c in COL_MAP.values():
        if c not in raw.columns:
            raw[c] = pd.NA

    dep_sched = parse_dt(raw["dep_sched_raw"])
    dep_actual = parse_dt(raw["dep_actual_raw"])
    arr_sched = parse_dt(raw["arr_sched_raw"])
    arr_actual = parse_dt(raw["arr_actual_raw"])
    ref = parse_dt(raw["referencia_raw"])

    flight_date = dep_sched.dt.date
    flight_date = flight_date.where(flight_date.notna(), ref.dt.date)
    flight_date = flight_date.where(flight_date.notna(), arr_sched.dt.date)

    fn_raw = raw["flight_number_raw"].astype(str).str.strip()
    fn_num = pd.to_numeric(fn_raw, errors="coerce").astype("Int64")

    carrier_icao = raw["carrier_icao"].astype(str).str.strip().str.upper()
    carrier_iata = carrier_icao.map(lambda x: al_map.get(x) if pd.notna(x) else None)
    carrier_iata = pd.Series(carrier_iata, index=raw.index).astype("string")
    overrides = {"GLO": "G3", "AZU": "AD", "TAM": "JJ", "ONE": "O6", "PTB": "2Z", "LTG": "LT", "TTL": "T0"}
    carrier_iata = carrier_iata.where(
        carrier_iata.notna() & (carrier_iata != "<NA>"), carrier_icao.map(overrides)
    )

    origin_icao = raw["origin_icao"].astype(str).str.strip().str.upper()
    dest_icao = raw["dest_icao"].astype(str).str.strip().str.upper()
    status = raw["situacao_voo"].map(map_status)
    cancelled = status == "CANCELLED"

    oc = raw["origin_desc"].map(parse_city_from_desc)
    dc = raw["dest_desc"].map(parse_city_from_desc)
    origin_city = pd.Series([t[0] for t in oc], index=raw.index, dtype="string")
    origin_state = pd.Series([t[1] for t in oc], index=raw.index, dtype="string")
    origin_country = pd.Series([t[2] for t in oc], index=raw.index, dtype="string")
    dest_city = pd.Series([t[0] for t in dc], index=raw.index, dtype="string")
    dest_state = pd.Series([t[1] for t in dc], index=raw.index, dtype="string")
    dest_country = pd.Series([t[2] for t in dc], index=raw.index, dtype="string")

    is_domestic = (
        origin_icao.str.startswith("SB", na=False) & dest_icao.str.startswith("SB", na=False)
    ) | (
        origin_country.astype(str).str.upper().eq("BRAZIL")
        & dest_country.astype(str).str.upper().eq("BRAZIL")
    )

    carrier_key = carrier_iata.fillna(carrier_icao).astype(str)
    out = pd.DataFrame(
        {
            "flight_date": pd.Series(flight_date, dtype="string"),
            "year": pd.to_datetime(flight_date).dt.year.astype("Int16"),
            "month": pd.to_datetime(flight_date).dt.month.astype("Int8"),
            "day": pd.to_datetime(flight_date).dt.day.astype("Int8"),
            "carrier_icao": carrier_icao.astype("string"),
            "carrier_iata": carrier_iata.astype("string"),
            "airline_name": raw["airline_name"].astype("string"),
            "flight_number": fn_num,
            "tipo_linha": raw["tipo_linha"].astype("string"),
            "seats": pd.to_numeric(raw["seats"], errors="coerce").astype("Int32"),
            "origin_icao": origin_icao.astype("string"),
            "origin_city": origin_city,
            "origin_state": origin_state,
            "dest_icao": dest_icao.astype("string"),
            "dest_city": dest_city,
            "dest_state": dest_state,
            "dep_delay_min": ((dep_actual - dep_sched).dt.total_seconds() / 60.0).astype("Float32"),
            "arr_delay_min": ((arr_actual - arr_sched).dt.total_seconds() / 60.0).astype("Float32"),
            "cancelled": cancelled,
            "status": status.astype("string"),
            "justificativa": raw["justificativa"].astype("string"),
            "is_domestic": is_domestic,
            "source_file": path.name,
            "source_year_folder": year,
        }
    )
    out["flight_key"] = (
        carrier_key
        + "-"
        + out["flight_number"].astype("string")
        + "|"
        + out["flight_date"].astype("string")
        + "|"
        + out["origin_icao"]
        + "|"
        + out["dest_icao"]
    ).astype("string")

    o_geo = ap_slim.rename(
        columns={
            "icao": "origin_icao",
            "iata_code": "origin_iata",
            "city_of": "origin_city_of",
            "country_of": "origin_country_of",
            "lat": "origin_lat",
            "lon": "origin_lon",
            "timezone": "origin_timezone",
        }
    )
    d_geo = ap_slim.rename(
        columns={
            "icao": "dest_icao",
            "iata_code": "dest_iata",
            "city_of": "dest_city_of",
            "country_of": "dest_country_of",
            "lat": "dest_lat",
            "lon": "dest_lon",
            "timezone": "dest_timezone",
        }
    )
    out = out.merge(o_geo, on="origin_icao", how="left")
    out = out.merge(d_geo, on="dest_icao", how="left")
    out["origin_city"] = out["origin_city"].fillna(out["origin_city_of"])
    out["dest_city"] = out["dest_city"].fillna(out["dest_city_of"])
    out = out[out["is_domestic"] == True].copy()
    out = out.dropna(subset=["flight_date", "carrier_icao", "origin_icao", "dest_icao"])
    out = out[
        out["origin_icao"].str.startswith("SB", na=False)
        & out["dest_icao"].str.startswith("SB", na=False)
    ]
    return out


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    year_start, year_end = year_range(argv)
    ensure_dirs()
    ap_slim, al_map = load_lookups()
    stats = []

    for year in range(year_start, year_end + 1):
        ydir = VRA_DIR / str(year)
        if not ydir.exists():
            print(f"SKIP missing year dir {ydir}")
            continue
        files = sorted(ydir.glob(f"VRA_{year}_*.csv"))
        if not files:
            print(f"SKIP no files for {year}")
            continue
        frames = []
        for path in files:
            print(f"  {path} ...", flush=True)
            frames.append(process_month(path, year, ap_slim, al_map))
        ydf = pd.concat(frames, ignore_index=True)
        ydf = ydf[(ydf["year"].astype(int) >= year - 1) & (ydf["year"].astype(int) <= year + 1)]
        ypath = WORK_DIR / f"domestic_flights_{year}.parquet"
        ydf.to_parquet(ypath, index=False, engine="pyarrow", compression="zstd")
        st = {
            "year": year,
            "rows": int(len(ydf)),
            "cancelled": int(ydf["cancelled"].sum()),
            "cancelled_pct": float(ydf["cancelled"].mean()) if len(ydf) else 0.0,
            "unique_routes": int(ydf[["origin_icao", "dest_icao"]].drop_duplicates().shape[0]),
            "unique_dest": int(ydf["dest_icao"].nunique()),
            "date_min": str(ydf["flight_date"].min()),
            "date_max": str(ydf["flight_date"].max()),
            "path": str(ypath),
        }
        stats.append(st)
        print(
            f"YEAR {year}: rows={st['rows']:,} cancel={st['cancelled_pct'] * 100:.2f}% "
            f"dest={st['unique_dest']} {st['date_min']}→{st['date_max']}"
        )

    if not stats:
        raise SystemExit("No year processed. Run download_vra.py first.")

    print("Concatenating years...")
    full = pd.concat(
        [pd.read_parquet(WORK_DIR / f"domestic_flights_{s['year']}.parquet") for s in stats],
        ignore_index=True,
    )
    full = full.sort_values(["flight_date", "carrier_icao", "origin_icao", "dest_icao"]).reset_index(
        drop=True
    )
    full_path = WORK_DIR / f"domestic_flights_{year_start}_{year_end}.parquet"
    full.to_parquet(full_path, index=False, engine="pyarrow", compression="zstd")
    full.to_parquet(FLIGHTS_HISTORY_PARQUET, index=False, engine="pyarrow", compression="zstd")

    need = full.dropna(subset=["dest_lat", "dest_lon"])[
        ["dest_icao", "dest_iata", "dest_city", "dest_lat", "dest_lon", "dest_timezone"]
    ].drop_duplicates("dest_icao")
    need = need.sort_values("dest_icao").reset_index(drop=True)
    need["date_min"] = f"{year_start}-01-01"
    need["date_max"] = f"{year_end}-12-31"
    need["n_flight_dates"] = (
        full.groupby("dest_icao")["flight_date"].nunique().reindex(need["dest_icao"]).values
    )
    man_path = WORK_DIR / "precip_manifest.parquet"
    need.to_parquet(man_path, index=False)

    summary = {
        "period": [f"{year_start}-01-01", f"{year_end}-12-31"],
        "scope": "domestic SB* -> SB* only",
        "years": stats,
        "total_rows": int(len(full)),
        "total_cancelled_pct": float(full["cancelled"].mean()),
        "unique_dest_br": int(len(need)),
        "full_path": str(full_path),
        "published_path": str(FLIGHTS_HISTORY_PARQUET),
        "manifest_path": str(man_path),
        "size_mb_full": round(full_path.stat().st_size / 1e6, 2),
    }
    (WORK_DIR / "build_flights_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("OK", FLIGHTS_HISTORY_PARQUET, f"{summary['size_mb_full']} MB")


if __name__ == "__main__":
    main()
