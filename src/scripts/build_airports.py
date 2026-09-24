#!/usr/bin/env python3
"""Build the ICAO reference table used by pricing/geo (city, UF, region, coords).

Sources, in priority order per field:
  * city / UF / region: exposure table + flights history (Portuguese pipeline)
  * coordinates: OurAirports, then OpenFlights, then the local parquet histories

The output (data/airports.csv) is committed so the app does not need the network
at runtime; this script is only needed to refresh coordinates.
"""

from __future__ import annotations

import csv
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from paths import (
    AIRPORTS_DAT,
    DATA_DIR,
    OPENFLIGHTS_AIRPORTS_URL,
    RAW_DIR,
    ensure_dirs,
)

OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OURAIRPORTS_CSV = RAW_DIR / "ourairports.csv"
OUTPUT_CSV = DATA_DIR / "airports.csv"
UA = "travel-insurance-data-pipeline/1.0"

# Brazilian ICAO prefixes. The product is domestic, so international codes are
# intentionally excluded from the reference table.
BRAZIL_ICAO_PREFIXES = ("SB", "SD", "SI", "SJ", "SN", "SS", "SW")

# Small airports absent from the public datasets, mapped by municipality.
MANUAL_COORDS = {
    "SBAS": (-22.638601, -50.455983),  # Assis - SP
    "SBFE": (-12.200694, -38.906164),  # Feira de Santana - BA
    "SBGS": (-25.184476, -50.143822),  # Ponta Grossa - PR
}

UF_REGION = {
    "AC": "N", "AM": "N", "AP": "N", "PA": "N", "RO": "N", "RR": "N", "TO": "N",
    "AL": "NE", "BA": "NE", "CE": "NE", "MA": "NE", "PB": "NE", "PE": "NE",
    "PI": "NE", "RN": "NE", "SE": "NE",
    "DF": "CO", "GO": "CO", "MT": "CO", "MS": "CO",
    "ES": "SE", "MG": "SE", "RJ": "SE", "SP": "SE",
    "PR": "S", "RS": "S", "SC": "S",
}


def _download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        data = urlopen(Request(url, headers={"User-Agent": UA}), timeout=120).read()
    except (HTTPError, URLError, TimeoutError):
        return False
    if not data:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def _region(uf: str) -> str:
    return UF_REGION.get(uf.strip().upper(), "")


def _exposure_meta() -> dict[str, dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    path = DATA_DIR / "route_month_exposure.parquet"
    if not path.exists():
        return meta
    df = pd.read_parquet(
        path,
        columns=["origin_icao", "origin_city", "origin_uf", "dest_icao", "dest_city", "dest_uf"],
    )
    for side in ("origin", "dest"):
        sub = df[[f"{side}_icao", f"{side}_city", f"{side}_uf"]].dropna(subset=[f"{side}_icao"])
        sub.columns = ["icao", "cidade", "uf"]
        for _, row in sub.iterrows():
            icao = str(row["icao"]).strip().upper()
            uf = str(row["uf"]).strip().upper() if pd.notna(row["uf"]) else ""
            meta.setdefault(
                icao,
                {
                    "cidade": str(row["cidade"]).strip() if pd.notna(row["cidade"]) else "",
                    "uf": uf,
                },
            )
    return meta


def _flight_coords() -> dict[str, dict[str, object]]:
    coords: dict[str, dict[str, object]] = {}
    path = DATA_DIR / "flights_history_full.parquet"
    if not path.exists():
        return coords
    df = pd.read_parquet(
        path,
        columns=[
            "origin_icao", "origin_city", "origin_state", "origin_country", "origin_lat", "origin_lon",
            "dest_icao", "dest_city", "dest_state", "dest_country", "dest_lat", "dest_lon",
        ],
    )
    for side in ("origin", "dest"):
        sub = df[
            [f"{side}_icao", f"{side}_city", f"{side}_state", f"{side}_country", f"{side}_lat", f"{side}_lon"]
        ].dropna(subset=[f"{side}_icao", f"{side}_lat", f"{side}_lon"])
        sub.columns = ["icao", "cidade", "uf", "pais", "lat", "lon"]
        for _, row in sub.drop_duplicates("icao").iterrows():
            icao = str(row["icao"]).strip().upper()
            coords.setdefault(
                icao,
                {
                    "lat": round(float(row["lat"]), 6),
                    "lon": round(float(row["lon"]), 6),
                    "cidade": str(row["cidade"]).strip() if pd.notna(row["cidade"]) else "",
                    "uf": str(row["uf"]).strip().upper() if pd.notna(row["uf"]) else "",
                    "pais": str(row["pais"]).strip() if pd.notna(row["pais"]) else "",
                },
            )
    return coords


def _ourairports_coords() -> dict[str, dict[str, object]]:
    coords: dict[str, dict[str, object]] = {}
    if not _download(OURAIRPORTS_URL, OURAIRPORTS_CSV):
        return coords
    with OURAIRPORTS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                lat = round(float(row["latitude_deg"]), 6)
                lon = round(float(row["longitude_deg"]), 6)
            except (KeyError, TypeError, ValueError):
                continue
            record = {"lat": lat, "lon": lon, "cidade": row.get("municipality", "") or "", "pais": "", "uf": ""}
            iso_region = (row.get("iso_region") or "").strip().upper()
            if iso_region.startswith("BR-"):
                record["uf"] = iso_region[3:]
            for key in (row.get("gps_code"), row.get("ident"), row.get("local_code")):
                if key:
                    coords.setdefault(key.strip().upper(), record)
    return coords


def _openflights_coords() -> dict[str, dict[str, object]]:
    coords: dict[str, dict[str, object]] = {}
    if not _download(OPENFLIGHTS_AIRPORTS_URL, AIRPORTS_DAT):
        return coords
    with AIRPORTS_DAT.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 8:
                continue
            icao = row[5].strip().upper()
            if not icao or icao == "\\N":
                continue
            try:
                lat, lon = round(float(row[6]), 6), round(float(row[7]), 6)
            except ValueError:
                continue
            coords.setdefault(icao, {"lat": lat, "lon": lon, "cidade": row[2].strip(), "pais": row[3].strip()})
    return coords


def _needed_icaos() -> set[str]:
    needed: set[str] = set()
    for name, cols in (
        ("route_month_exposure.parquet", ["origin_icao", "dest_icao"]),
        ("flights_history_full.parquet", ["origin_icao", "dest_icao"]),
    ):
        path = DATA_DIR / name
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=cols)
        for col in cols:
            needed |= {str(v).strip().upper() for v in df[col].dropna()}
    return {icao for icao in needed if icao.startswith(BRAZIL_ICAO_PREFIXES)}


def main(argv: list[str] | None = None) -> None:
    ensure_dirs()
    needed = _needed_icaos()
    if not needed:
        raise SystemExit("No exposure/flights parquet found in data/. Nothing to derive.")

    meta = _exposure_meta()
    flights = _flight_coords()
    openflights = _openflights_coords()
    ourairports = _ourairports_coords()

    rows: list[list[object]] = []
    missing: list[str] = []
    for icao in sorted(needed):
        m, f, o, a = meta.get(icao, {}), flights.get(icao, {}), openflights.get(icao), ourairports.get(icao)
        coords = None
        for candidate in (f, a, o):
            if candidate and candidate.get("lat") is not None:
                coords = candidate
                break
        if coords is None and icao in MANUAL_COORDS:
            lat, lon = MANUAL_COORDS[icao]
            coords = {"lat": lat, "lon": lon}
        if coords is None:
            missing.append(icao)
            continue
        cidade = m.get("cidade") or f.get("cidade") or (a or {}).get("cidade") or (o or {}).get("cidade") or ""
        uf = m.get("uf") or f.get("uf") or (a or {}).get("uf") or ""
        pais = f.get("pais") or (o or {}).get("pais") or ("Brazil" if uf else "")
        rows.append([icao, cidade, uf, _region(uf), coords["lat"], coords["lon"], "", pais])

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["icao", "cidade", "uf", "regiao", "lat", "lon", "ils_cat", "pais"])
        writer.writerows(rows)

    print(f"Wrote {OUTPUT_CSV} rows {len(rows)}")
    if missing:
        print(f"WARNING: {len(missing)} ICAOs without coordinates: {missing}")


if __name__ == "__main__":
    main()
