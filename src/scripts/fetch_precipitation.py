#!/usr/bin/env python3
"""Download daily precipitation from Open-Meteo Archive for BR destinations."""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from paths import (
    CACHE_DIR,
    PRECIPITATION_HISTORY_PARQUET,
    WORK_DIR,
    ensure_dirs,
    year_range,
)

BASE = "https://archive-api.open-meteo.com/v1/archive"
THRESHOLDS = [5.0, 10.0, 20.0, 50.0]
UA = "travel-insurance-data-pipeline/1.0"


def fetch_one(lat, lon, start, end, timezone, retries=6):
    tz = (
        timezone
        if pd.notna(timezone) and str(timezone).strip() and str(timezone) != "<NA>"
        else "America/Sao_Paulo"
    )
    end_use = min(str(end), (date.today() - timedelta(days=5)).isoformat())
    start_use = str(start)
    if start_use > end_use:
        end_use = start_use

    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "start_date": start_use,
        "end_date": end_use,
        "daily": "precipitation_sum",
        "timezone": tz,
    }
    url = f"{BASE}?{urlencode(params)}"
    cache_key = (
        f"{round(float(lat), 4)}_{round(float(lon), 4)}_{start_use}_{end_use}_"
        f"{tz.replace('/', '_')}.json"
    )
    cache_path = CACHE_DIR / cache_key
    if cache_path.exists() and cache_path.stat().st_size > 50:
        return json.loads(cache_path.read_text(encoding="utf-8")), url, True

    last_err = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cache_path.write_text(json.dumps(data), encoding="utf-8")
            return data, url, False
        except HTTPError as e:
            last_err = e
            wait = 2 ** attempt
            if e.code == 429:
                wait = max(wait, 30)
            print(f"  HTTP {e.code} attempt {attempt + 1}, sleep {wait}s")
            time.sleep(wait)
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  err {type(e).__name__}: {e}; sleep {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed after retries: {last_err}")


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    year_start, year_end = year_range(argv)
    ensure_dirs()
    start = f"{year_start}-01-01"
    end = f"{year_end}-12-31"

    man_path = WORK_DIR / "precip_manifest.parquet"
    if not man_path.exists():
        raise SystemExit(f"Manifest missing: {man_path}. Run build_flights.py first.")

    manifest = pd.read_parquet(man_path)
    print(f"Destinations: {len(manifest)} | range {start} → {end}")

    rows = []
    errors = []
    api_calls = 0
    cache_hits = 0
    t0 = time.time()

    for i, r in manifest.iterrows():
        dest_icao = r["dest_icao"]
        lat, lon = r["dest_lat"], r["dest_lon"]
        if pd.isna(lat) or pd.isna(lon):
            errors.append({"dest_icao": dest_icao, "error": "missing lat/lon"})
            continue
        print(
            f"[{i + 1}/{len(manifest)}] {dest_icao} {r.get('dest_city')} "
            f"({lat:.3f},{lon:.3f}) ...",
            flush=True,
        )
        try:
            data, url, from_cache = fetch_one(lat, lon, start, end, r.get("dest_timezone"))
            if from_cache:
                cache_hits += 1
            else:
                api_calls += 1
                time.sleep(0.4)
            daily = data.get("daily") or {}
            times = daily.get("time") or []
            precip = daily.get("precipitation_sum") or []
            lat_used = data.get("latitude", lat)
            lon_used = data.get("longitude", lon)
            elev = data.get("elevation")
            tz_used = data.get("timezone") or r.get("dest_timezone")
            utc_offset = data.get("utc_offset_seconds")
            n = 0
            for d, p in zip(times, precip):
                rows.append(
                    {
                        "dest_icao": dest_icao,
                        "dest_iata": r.get("dest_iata"),
                        "dest_city": r.get("dest_city"),
                        "date": d,
                        "precip_mm": None if p is None else float(p),
                        "lat_request": float(lat),
                        "lon_request": float(lon),
                        "lat_grid": float(lat_used) if lat_used is not None else None,
                        "lon_grid": float(lon_used) if lon_used is not None else None,
                        "elevation_m": float(elev) if elev is not None else None,
                        "timezone": str(tz_used) if tz_used is not None else None,
                        "utc_offset_seconds": int(utc_offset) if utc_offset is not None else None,
                        "from_cache": from_cache,
                        "source": "Open-Meteo_Archive",
                    }
                )
                n += 1
            print(f"  -> {n} days cache={from_cache}")
        except Exception as e:
            print(f"  FAIL {dest_icao}: {e}")
            errors.append({"dest_icao": dest_icao, "error": str(e)})

    elapsed = time.time() - t0
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("No precipitation data")

    df["date"] = df["date"].astype("string")
    dt = pd.to_datetime(df["date"])
    df["year"] = dt.dt.year.astype("Int16")
    df["month"] = dt.dt.month.astype("Int8")
    df["day"] = dt.dt.day.astype("Int8")
    df["precip_mm"] = pd.to_numeric(df["precip_mm"], errors="coerce").astype("Float32")
    for thr in THRESHOLDS:
        df[f"above_{int(thr)}mm"] = (df["precip_mm"] >= thr).astype("boolean")

    df = df.sort_values(["dest_icao", "date"]).reset_index(drop=True)
    work_path = WORK_DIR / f"precipitation_{year_start}_{year_end}.parquet"
    df.to_parquet(work_path, index=False, engine="pyarrow", compression="zstd")
    df.to_parquet(PRECIPITATION_HISTORY_PARQUET, index=False, engine="pyarrow", compression="zstd")

    summary = {
        "rows": int(len(df)),
        "destinations": int(df["dest_icao"].nunique()),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
        "api_calls_live": api_calls,
        "cache_hits": cache_hits,
        "errors": errors,
        "elapsed_sec": round(elapsed, 1),
        "mean_precip_mm": float(df["precip_mm"].mean(skipna=True)),
        "pct_days_ge_10mm": float((df["precip_mm"] >= 10).mean()),
        "path": str(work_path),
        "published_path": str(PRECIPITATION_HISTORY_PARQUET),
        "note": "1 API call per destination for the full date range",
    }
    (WORK_DIR / "build_precip_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("OK", PRECIPITATION_HISTORY_PARQUET)


if __name__ == "__main__":
    main()
