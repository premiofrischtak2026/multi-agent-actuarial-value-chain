"""Challenger: compare interpolation/regression methods (article 7.3).

Distance-based methods (IDW, nearest, regional, ordinary kriging) are evaluated
leave-one-out. Hierarchical (mixed-effects) and gradient-boosting models use
K-fold cross-validation. All scores are MAE/RMSE of the combined frequency.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from pricing.geo import AirportTable, distance_between
from pricing.idw import idw_weights, weighted_mean
from pricing.tables import ExposureTable


@dataclass
class MethodScore:
    metodo: str
    mae: float
    rmse: float
    n: int


def _combined(row) -> float:
    cancel = 0.0 if pd.isna(row["freq_cancellation"]) else float(row["freq_cancellation"])
    rain = 0.0 if pd.isna(row["freq_rain_10mm"]) else float(row["freq_rain_10mm"])
    return cancel + rain


def _kriging_predict(candidates: list[tuple[float, float, Any, Any]], k: int) -> float:
    """Ordinary kriging with an exponential variogram (transparent defaults)."""
    subset = sorted(candidates, key=lambda c: c[0])[:k]
    if len(subset) < 2:
        return subset[0][1]
    values = np.array([c[1] for c in subset], dtype=float)
    coordinates = [c[2] for c in subset]
    n = len(subset)
    pairwise = np.array(
        [[distance_between(coordinates[i], coordinates[j]) for j in range(n)] for i in range(n)]
    )
    sill = float(values.var()) or 1e-9
    max_h = float(pairwise.max()) or 1.0
    range_ = max(max_h / 3.0, 1.0)

    def gamma(h: float) -> float:
        return sill * (1.0 - np.exp(-h / range_))

    A = np.zeros((n + 1, n + 1))
    for i in range(n):
        for j in range(n):
            A[i, j] = gamma(pairwise[i, j])
        A[i, n] = 1.0
        A[n, i] = 1.0
    b = np.array([gamma(c[0]) for c in subset] + [1.0])
    try:
        weights = np.linalg.solve(A, b)[:n]
    except np.linalg.LinAlgError:
        return subset[0][1]
    return float(np.dot(weights, values))


def _global_cv_scores(df: pd.DataFrame, value_col: str, method: str, kfold: int) -> tuple[float, float, int]:
    errors: list[float] = []
    shuffled = df.sample(frac=1.0, random_state=0)
    folds = np.array_split(shuffled.index.to_numpy(), kfold)
    for fold in folds:
        test = shuffled.loc[fold]
        train = shuffled.drop(fold)
        if train.empty or test.empty:
            continue
        if method == "hierarchical":
            import warnings

            import statsmodels.formula.api as smf

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = smf.mixedlm(f"{value_col} ~ 1", train, groups=train["dest_region"].fillna("??")).fit()
            grand = float(model.params["Intercept"])
            random_effects = model.random_effects

            def _re_value(key: str) -> float:
                value = random_effects.get(key)
                if value is None:
                    return 0.0
                if hasattr(value, "iloc"):
                    return float(value.iloc[0])
                return float(value[0])

            predictions = [grand + _re_value(str(r)) for r in test["dest_region"].fillna("??")]
        else:
            from sklearn.ensemble import GradientBoostingRegressor

            features = pd.get_dummies(
                pd.DataFrame({"month": test["month"], "region": test["dest_region"].fillna("??")}),
                columns=["region"],
            )
            train_features = pd.get_dummies(
                pd.DataFrame({"month": train["month"], "region": train["dest_region"].fillna("??")}),
                columns=["region"],
            ).reindex(columns=features.columns, fill_value=0.0)
            regressor = GradientBoostingRegressor(random_state=0)
            regressor.fit(train_features.to_numpy(dtype=float), train[value_col].to_numpy(dtype=float))
            predictions = regressor.predict(features.to_numpy(dtype=float))
        errors.extend(abs(float(p) - float(a)) for p, a in zip(predictions, test[value_col], strict=False))
    if not errors:
        return (float("nan"), float("nan"), 0)
    mae = sum(errors) / len(errors)
    rmse = (sum(e * e for e in errors) / len(errors)) ** 0.5
    return (mae, rmse, len(errors))


def compare_methods(
    table: ExposureTable,
    airport_table: AirportTable,
    *,
    month: int = 9,
    min_flights: int = 1,
    k: int = 3,
    kfold: int = 5,
) -> list[dict[str, Any]]:
    df = table.dataframe
    cells = df[(df["month"] == month) & (df["n_flights"] >= min_flights)].copy()
    cells = cells.sort_values(["dest_icao", "year"], ascending=[True, False]).drop_duplicates("dest_icao")

    distance_errors: dict[str, list[float]] = {"idw": [], "nearest": [], "regional": [], "kriging": []}
    for _, target in cells.iterrows():
        target_airport = airport_table.get(str(target["dest_icao"]))
        if target_airport is None:
            continue
        candidates: list[tuple[float, float, Any, Any]] = []
        for _, other in cells[cells["dest_icao"] != target["dest_icao"]].iterrows():
            other_airport = airport_table.get(str(other["dest_icao"]))
            if other_airport is None:
                continue
            candidates.append(
                (distance_between(other_airport, target_airport), _combined(other), other_airport, other.get("dest_region"))
            )
        if not candidates:
            continue
        candidates.sort(key=lambda c: c[0])
        actual = _combined(target)
        nearest = candidates[0][1]
        subset = candidates[:k]
        idw_pred = weighted_mean([c[1] for c in subset], idw_weights([c[0] for c in subset], [1.0] * len(subset)))
        region = target.get("dest_region")
        pool = [c[1] for c in candidates if c[3] == region] or [c[1] for c in candidates]
        regional = median(pool)
        kriging = _kriging_predict(candidates, k)

        distance_errors["idw"].append(abs(idw_pred - actual))
        distance_errors["nearest"].append(abs(nearest - actual))
        distance_errors["regional"].append(abs(regional - actual))
        distance_errors["kriging"].append(abs(kriging - actual))

    scores: list[MethodScore] = []
    for metodo, errs in distance_errors.items():
        if not errs:
            continue
        mae = sum(errs) / len(errs)
        rmse = (sum(e * e for e in errs) / len(errs)) ** 0.5
        scores.append(MethodScore(metodo, round(mae, 6), round(rmse, 6), len(errs)))

    global_df = df[df["n_flights"] >= min_flights].copy()
    global_df["_value"] = global_df.apply(_combined, axis=1)
    for method in ("hierarchical", "gradient_boosting"):
        try:
            mae, rmse, n = _global_cv_scores(global_df, "_value", method, kfold)
        except Exception:  # noqa: BLE001 - optional method/dependency
            continue
        if n:
            scores.append(MethodScore(method, round(mae, 6), round(rmse, 6), n))

    return [s.__dict__ for s in sorted(scores, key=lambda s: s.mae)]
