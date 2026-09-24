import pytest

from pricing.geo import AirportTable, distance_between
from pricing.network import neighborhood, risk_distance
from pricing.similarity import (
    AirportProfile,
    ProfileTable,
    cosine_similarity,
    gamma_from_features,
    mahalanobis_distance,
    make_gamma_provider,
)
from pricing.tables import ExposureTable

HEADER = "year,month,rota,origin_icao,dest_icao,n_voos,freq_cancelamento,freq_chuva_10mm"


def test_cosine_similarity():
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


def test_mahalanobis_identity_is_euclidean():
    identity = [[1, 0], [0, 1]]
    assert mahalanobis_distance([0, 0], [3, 4], identity) == pytest.approx(5.0)


def test_gamma_from_features():
    a = AirportProfile("AAAA", 0.1, 0.2, 0.3)
    assert gamma_from_features(a, a) == pytest.approx(1.0)
    b = AirportProfile("BBBB", 0.5, 0.2, 0.3)
    assert gamma_from_features(a, b) > 1.0


def test_profile_table_and_provider(tmp_path):
    csv = tmp_path / "profile.csv"
    csv.write_text("icao,clima,atraso,infra\nSBGR,0.2,0.1,0.9\nSBFI,0.6,0.3,0.4\n", encoding="utf-8")
    profiles = ProfileTable.load(csv)
    assert len(profiles) == 2
    airports = AirportTable()
    provider = make_gamma_provider(profiles)
    gamma = provider(airports.require("SBFI"), airports.require("SBGR"))
    assert gamma > 1.0
    # unknown ICAO falls back to 1.0
    assert make_gamma_provider(profiles)(airports.require("SBGR"), airports.require("SBPA")) == 1.0


def test_neighborhood_uses_gamma_provider(tmp_path):
    exposure = tmp_path / "e.csv"
    exposure.write_text(
        HEADER + "\n2025,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02\n2025,9,SBGR→SBCT,SBGR,SBCT,600,0.02,0.03\n",
        encoding="utf-8",
    )
    table = ExposureTable(csv_path=exposure)
    profile = tmp_path / "p.csv"
    profile.write_text("icao,clima,atraso,infra\nSBFI,0.1,0.1,0.1\nSBCT,0.9,0.9,0.9\n", encoding="utf-8")
    provider = make_gamma_provider(ProfileTable.load(profile))
    anchors = neighborhood("SBPA", 9, table=table, airport_table=AirportTable(), k=3, gamma_provider=provider)
    assert anchors and all(a.gamma >= 1.0 for a in anchors)


def test_risk_distance_adds_mahalanobis():
    airports = AirportTable()
    sbgr, sbfi = airports.require("SBGR"), airports.require("SBFI")
    profiles = ProfileTable(
        {
            "SBGR": AirportProfile("SBGR", 0.2, 0.1, 0.9),
            "SBFI": AirportProfile("SBFI", 0.6, 0.3, 0.4),
        }
    )
    identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    base = distance_between(sbgr, sbfi)
    assert risk_distance(sbgr, sbfi, profiles=profiles, covariance_inv=identity) > base
    assert risk_distance(sbgr, sbfi) == pytest.approx(base)
