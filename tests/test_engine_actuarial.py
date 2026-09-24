from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pricing.engine import PriceEngine
from pricing.geo import AirportTable, haversine_km
from pricing.glm import FrequencyGLM, SeverityGLM
from pricing.idw import idw_weights, weighted_mean
from pricing.interpolation import interpolate_frequency, interpolate_values
from pricing.network import Anchor, neighborhood
from pricing.tables import ExposureTable
from schemas import BookingInput

EXPOSURE_HEADER = "year,month,rota,origin_icao,dest_icao,n_voos,freq_cancelamento,freq_chuva_10mm"
JERI_ANCHORS = [
    # artigo 4.7 / ancoras_jericoacoara.json
    (48.2, 1.0, 0.0120, 4200.0),
    (122.5, 3.3488, 0.0145, 5100.0),
    (285.0, 11.4175, 0.0180, 6800.0),
]


def test_haversine_basic():
    gr = AirportTable().require("SBGR")
    gl = AirportTable().require("SBGL")
    assert haversine_km(gr.lat, gr.lon, gr.lat, gr.lon) == 0
    assert haversine_km(gr.lat, gr.lon, gl.lat, gl.lon) == pytest.approx(
        haversine_km(gl.lat, gl.lon, gr.lat, gr.lon)
    )
    assert 250 < haversine_km(gr.lat, gr.lon, gl.lat, gl.lon) < 450  # GRU-GIG ~ 340 km


def test_idw_weights_simple():
    weights = idw_weights([1.0, 2.0], [1.0, 1.0], power=2.0)
    assert weights == pytest.approx([0.8, 0.2])
    assert sum(weights) == pytest.approx(1.0)


def test_jericoacoara_weights_and_premium():
    distances = [d for d, _, _, _ in JERI_ANCHORS]
    gammas = [g for _, g, _, _ in JERI_ANCHORS]
    weights = idw_weights(distances, gammas, power=2.0)
    assert weights == pytest.approx([0.542, 0.281, 0.177], abs=0.002)

    freq, _ = interpolate_values([f for _, _, f, _ in JERI_ANCHORS], distances, gammas)
    sev, _ = interpolate_values([s for _, _, _, s in JERI_ANCHORS], distances, gammas)
    assert freq == pytest.approx(0.01376, abs=1e-4)
    assert sev == pytest.approx(4912.41, rel=1e-2)
    assert freq * sev == pytest.approx(67.59, abs=0.5)


def _table(tmp_path: Path, rows: list[str]) -> ExposureTable:
    csv = tmp_path / "exposure.csv"
    csv.write_text(EXPOSURE_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return ExposureTable(csv_path=csv)


def test_neighborhood_sorts_by_distance(tmp_path):
    table = _table(
        tmp_path,
        [
            "2025,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02",
            "2025,9,SBGR→SBCT,SBGR,SBCT,600,0.02,0.03",
        ],
    )
    anchors = neighborhood("SBPA", 9, table=table, airport_table=AirportTable(), k=3)
    assert anchors and {a.icao for a in anchors} == {"SBFI", "SBCT"}
    distances = [a.distancia_km for a in anchors]
    assert distances == sorted(distances)


def test_interpolate_frequency_from_anchors():
    anchors = [
        Anchor("SBFI", "Foz", 100.0, 1.0, 0.01, 0.02, 500),
        Anchor("SBCT", "Curitiba", 200.0, 1.0, 0.03, 0.06, 500),
    ]
    result = interpolate_frequency(anchors)
    assert result.freq_cancel == pytest.approx((0.01 * 0.8) + (0.03 * 0.2))
    assert sum(result.weights) == pytest.approx(1.0)


def test_engine_uses_idw_for_gap(tmp_path):
    table = _table(
        tmp_path,
        [
            "2025,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02",
            "2025,9,SBGR→SBCT,SBGR,SBCT,600,0.02,0.03",
        ],
    )
    booking = BookingInput.model_validate(
        {
            "booking_id": "BK-I",
            "flight_date": "2025-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBPA",
            "ticket_value_brl": 1000.0,
            "accommodation_value_brl": 500.0,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "Porto Alegre", "start": "2025-09-10", "end": "2025-09-12"},
        }
    )
    result = PriceEngine(table=table).price(booking)
    assert result.sparsity_flag is True
    assert any(s.tipo == "idw" for s in result.fontes)
    assert "IDW" in (result.aviso or "")
    assert result.freq_cancel != PriceEngine.DEFAULT_FREQ_CANCEL


def test_frequency_glm_poisson_and_negbinomial():
    rng = np.random.default_rng(0)
    x = pd.DataFrame({"season": rng.normal(size=200)})
    y = pd.Series(rng.poisson(lam=np.exp(0.2 + 0.5 * x["season"])))
    for family in ("poisson", "negbinomial"):
        fit = FrequencyGLM(family=family).fit(x, y)
        assert fit.n_obs == 200
    predictions = FrequencyGLM("poisson")
    predictions.fit(x, y)
    assert len(predictions.predict(x)) == 200 and (predictions.predict(x) >= 0).all()


def test_severity_glm_gamma_and_lognormal():
    rng = np.random.default_rng(1)
    x = pd.DataFrame({"exposure": rng.uniform(1, 10, size=150)})
    y = pd.Series(rng.gamma(shape=2.0, scale=500.0 * x["exposure"]))
    for family in ("gamma", "lognormal"):
        model = SeverityGLM(family=family)
        model.fit(x, y)
        predictions = model.predict(x)
        assert len(predictions) == 150 and (predictions > 0).all()
