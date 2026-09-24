#!/usr/bin/env python3
"""Calibrate the frequency GLMs from the exposure series and persist them.

Writes data/models/frequency_glm.json (used by PriceEngine when provided).
"""

from __future__ import annotations

import sys
from pathlib import Path

from paths import DATA_DIR

sys.path.insert(0, str(DATA_DIR.parent))

from pricing.calibration import calibrate  # noqa: E402
from pricing.tables import ExposureTable  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    table = ExposureTable()
    model = calibrate(table, min_flights=50)
    print("Wrote", DATA_DIR / "models" / "frequency_glm.json", "with", len(model.columns), "features")


if __name__ == "__main__":
    main()
