#!/usr/bin/env python3
"""Download ANAC VRA monthly CSVs and OpenFlights airport/airline lookups."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from paths import (
    AIRLINES_DAT,
    AIRPORTS_DAT,
    ANAC_VRA_BASE,
    OPENFLIGHTS_AIRLINES_URL,
    OPENFLIGHTS_AIRPORTS_URL,
    VRA_DIR,
    ensure_dirs,
    year_range,
)

UA = "travel-insurance-data-pipeline/1.0"


def fetch(url: str, dest: Path, retries: int = 4, timeout: int = 180) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return False
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if not data:
                raise RuntimeError("empty response")
            part = dest.with_suffix(dest.suffix + ".part")
            part.write_bytes(data)
            part.replace(dest)
            return True
        except HTTPError as exc:
            last_err = exc
            if exc.code == 404:
                print(f"  skip 404 {url}")
                return False
            wait = 2 ** attempt
            if exc.code == 429:
                wait = max(wait, 30)
            print(f"  HTTP {exc.code} attempt {attempt + 1}, sleep {wait}s")
            time.sleep(wait)
        except (URLError, TimeoutError, RuntimeError, OSError) as exc:
            last_err = exc
            wait = 2 ** attempt
            print(f"  {type(exc).__name__}: {exc}; sleep {wait}s")
            time.sleep(wait)
    print(f"  FAIL {url}: {last_err}")
    return False


def download_lookups() -> None:
    for url, dest, label in (
        (OPENFLIGHTS_AIRPORTS_URL, AIRPORTS_DAT, "airports.dat"),
        (OPENFLIGHTS_AIRLINES_URL, AIRLINES_DAT, "airlines.dat"),
    ):
        print(f"GET {label}")
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  already present ({dest.stat().st_size} bytes)")
            continue
        fetch(url, dest)


def download_vra(year_start: int, year_end: int) -> None:
    ok = skip = fail = 0
    for year in range(year_start, year_end + 1):
        year_dir = VRA_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        for month in range(1, 13):
            name = f"VRA_{year}_{month:02d}.csv"
            dest = year_dir / name
            if dest.exists() and dest.stat().st_size > 0:
                skip += 1
                continue
            url = f"{ANAC_VRA_BASE}/{year}/{name}"
            print(f"GET {url}")
            if fetch(url, dest):
                ok += 1
                print(f"  OK {dest.stat().st_size / 1e6:.1f} MB")
            elif dest.exists() and dest.stat().st_size > 0:
                ok += 1
            else:
                fail += 1
    n_files = len(list(VRA_DIR.glob("*/VRA_*.csv")))
    print(f"DONE downloaded={ok} skipped={skip} failed={fail} files={n_files}")


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    year_start, year_end = year_range(argv)
    ensure_dirs()
    print(f"Lookups + ANAC VRA {year_start}–{year_end}")
    download_lookups()
    download_vra(year_start, year_end)


if __name__ == "__main__":
    main()
