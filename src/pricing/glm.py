"""GLM frequency/severity models (article section 4.1).

Frequency: Poisson or Negative Binomial (log link).
Severity: Gamma (log link) or Log-Normal (log-OLS).

The models are deliberately thin wrappers around statsmodels so the actuarial
engine can fit/predict with versioned coefficients. Models are only *trained*
when a labelled dataset is supplied; the pricing path uses the exposure table
until such a dataset exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

FrequencyFamily = Literal["poisson", "negbinomial"]
SeverityFamily = Literal["gamma", "lognormal"]


def _statsmodels():
    try:
        import statsmodels.api as sm
    except ImportError as exc:  # pragma: no cover
        raise ImportError("statsmodels é necessário para os GLMs (Fase 3).") from exc
    return sm


@dataclass
class GLMFit:
    family: str
    params: dict[str, float]
    n_obs: int
    converged: bool
    extra: dict[str, float] = field(default_factory=dict)


class FrequencyGLM:
    def __init__(self, family: FrequencyFamily = "poisson", add_constant: bool = True, negbinomial_alpha: float = 1.0):
        if family not in ("poisson", "negbinomial"):
            raise ValueError(f"Família de frequência inválida: {family}")
        self.family = family
        self.add_constant = add_constant
        self.negbinomial_alpha = negbinomial_alpha
        self._result = None
        self._columns: list[str] = []

    def fit(self, X: pd.DataFrame, y: pd.Series, exposure: pd.Series | None = None) -> GLMFit:
        sm = _statsmodels()
        design = sm.add_constant(X) if self.add_constant else X
        self._columns = list(design.columns)
        if self.family == "poisson":
            model = sm.GLM(y, design, family=sm.families.Poisson(), offset=np.log(exposure) if exposure is not None else None)
        else:
            model = sm.GLM(y, design, family=sm.families.NegativeBinomial(alpha=self.negbinomial_alpha))
        self._result = model.fit()
        return GLMFit(
            family=self.family,
            params={str(k): float(v) for k, v in self._result.params.items()},
            n_obs=int(self._result.nobs),
            converged=bool(self._result.converged),
        )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._result is None:
            raise RuntimeError("Modelo não ajustado")
        design = X if not self.add_constant or "const" in X.columns else _statsmodels().add_constant(X)
        return np.asarray(self._result.predict(design))


class SeverityGLM:
    def __init__(self, family: SeverityFamily = "gamma"):
        if family not in ("gamma", "lognormal"):
            raise ValueError(f"Família de severidade inválida: {family}")
        self.family = family
        self._result = None
        self._columns: list[str] = []
        self._sm = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> GLMFit:
        sm = _statsmodels()
        self._sm = sm
        design = sm.add_constant(X)
        self._columns = list(design.columns)
        if self.family == "gamma":
            model = sm.GLM(y, design, family=sm.families.Gamma(link=sm.families.links.Log()))
        else:
            model = sm.OLS(np.log(y), design)
        self._result = model.fit()
        return GLMFit(
            family=self.family,
            params={str(k): float(v) for k, v in self._result.params.items()},
            n_obs=int(self._result.nobs),
            converged=True,
        )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._result is None:
            raise RuntimeError("Modelo não ajustado")
        design = X if "const" in X.columns else _statsmodels().add_constant(X)
        prediction = np.asarray(self._result.predict(design))
        if self.family == "lognormal":
            return np.exp(prediction)
        return prediction
