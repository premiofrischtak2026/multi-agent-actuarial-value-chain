"""Calibrate and version the frequency GLMs from the exposure series (article 4.1).

Two GLMs are fit with a log exposure offset:
  * cancellation  ~ season/month + destination region
  * rain > 10 mm  ~ season/month + destination region

Coefficients are persisted to ``data/models/`` so the pricing engine can use the
approved version. When no model file exists, pricing falls back to the cell/IDW.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from config import MODELS_DIR
from pricing.glm import FrequencyGLM
from pricing.tables import ExposureTable

MODEL_FILE = MODELS_DIR / "frequency_glm.json"
EXPOSURE_COLUMNS = {"month", "dest_region", "n_flights", "n_cancelled", "n_trigger_10mm"}


def _features(df: pd.DataFrame) -> pd.DataFrame:
    month = pd.get_dummies(df["month"].astype(int).astype("category"), prefix="m")
    region = pd.get_dummies(df["dest_region"].fillna("??").astype(str), prefix="r")
    return pd.concat([month, region], axis=1).astype(float)


def _train(table: ExposureTable, min_flights: int = 50) -> tuple[pd.DataFrame, FrequencyGLM, FrequencyGLM]:
    df = table.dataframe
    if not EXPOSURE_COLUMNS.issubset(df.columns):
        raise ValueError(f"Exposição sem colunas necessárias: {sorted(EXPOSURE_COLUMNS)}")
    df = df[df["n_flights"] >= min_flights].dropna(subset=["n_cancelled", "n_trigger_10mm"]).copy()
    if df.empty:
        raise ValueError("Sem células suficientes para calibrar")
    X = _features(df)
    exposure = df["n_flights"].astype(float)
    cancel_model = FrequencyGLM("poisson")
    cancel_model.fit(X, df["n_cancelled"].astype(float), exposure)
    rain_model = FrequencyGLM("poisson")
    rain_model.fit(X, df["n_trigger_10mm"].astype(float), exposure)
    return X, cancel_model, rain_model


def _fit_to_dict(fit) -> dict[str, Any]:
    return {"family": fit.family, "params": fit.params, "n_obs": fit.n_obs, "converged": fit.converged}


@dataclass
class FrequencyModel:
    columns: list[str]
    cancel: dict[str, Any]
    rain: dict[str, Any]

    def _design(self, month: int, region: str) -> pd.DataFrame:
        row = {c: 0.0 for c in self.columns}
        row["const"] = 1.0
        for c in (f"m_{month}", f"r_{region}"):
            if c in row:
                row[c] = 1.0
        return pd.DataFrame([row], columns=self.columns)

    def _rate(self, params: dict[str, float], month: int, region: str) -> float:
        design = self._design(month, region)
        import numpy as np

        linear = float(np.dot(design.to_numpy()[0], [params.get(c, 0.0) for c in self.columns]))
        return float(np.exp(linear))

    def predict(self, month: int, region: str) -> tuple[float, float]:
        return (
            self._rate(self.cancel["params"], month, region),
            self._rate(self.rain["params"], month, region),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"columns": self.columns, "cancel": self.cancel, "rain": self.rain}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FrequencyModel":
        return cls(columns=payload["columns"], cancel=payload["cancel"], rain=payload["rain"])

    def save(self, path: Path | None = None) -> Path:
        path = path or MODEL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "FrequencyModel | None":
        path = path or MODEL_FILE
        if not Path(path).exists():
            return None
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def calibrate(table: ExposureTable, *, min_flights: int = 50, path: Path | None = None) -> FrequencyModel:
    X, cancel_model, rain_model = _train(table, min_flights)
    model = FrequencyModel(
        columns=["const", *list(X.columns)],
        cancel=_fit_to_dict(_freq_fit(cancel_model)),
        rain=_fit_to_dict(_freq_fit(rain_model)),
    )
    model.save(path)
    return model


def _freq_fit(model: FrequencyGLM):
    from pricing.glm import GLMFit

    result = model._result
    return GLMFit(
        family=model.family,
        params={str(k): float(v) for k, v in result.params.items()},
        n_obs=int(result.nobs),
        converged=bool(result.converged),
    )
