#!/usr/bin/env bash
# Rebuild ANAC + Open-Meteo history and the exposure table used by pricing.
#
# Usage:
#   ./run_all.sh
#   YEAR_START=2016 YEAR_END=2026 ./run_all.sh
#
# Requires: python3, pandas, pyarrow, numpy. Network access for ANAC and Open-Meteo.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export YEAR_START="${YEAR_START:-2016}"
export YEAR_END="${YEAR_END:-$(date +%Y)}"

echo "=== Data pipeline ${YEAR_START}–${YEAR_END} ==="

echo "=== 1/6 Download ANAC VRA + OpenFlights lookups ==="
python3 download_vra.py --year-start "$YEAR_START" --year-end "$YEAR_END"

echo "=== 2/6 Build domestic flights parquet ==="
python3 build_flights.py --year-start "$YEAR_START" --year-end "$YEAR_END"

echo "=== 3/6 Fetch Open-Meteo precipitation ==="
python3 fetch_precipitation.py --year-start "$YEAR_START" --year-end "$YEAR_END"

echo "=== 4/6 Build route/month exposure ==="
python3 build_exposure.py --year-start "$YEAR_START" --year-end "$YEAR_END"

echo "=== 5/6 Build airport reference table ==="
python3 build_airports.py

echo "=== 6/6 Build golden exposure sample ==="
python3 build_golden.py

echo "=== Done. Published files in ../data/ ==="
ls -lh ../data/*.parquet ../data/*.csv 2>/dev/null || true
