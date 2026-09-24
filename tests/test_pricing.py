from pathlib import Path

import pytest

from config import ANNEX_I_REFERENCE, TECH_NOTE_VERSION
from monitoring.claims import rain_trigger
from pricing.engine import PriceEngine
from pricing.tables import ExposureTable
from schemas import BookingInput, PricingMethod

EXPOSURE_HEADER = "year,month,rota,origin_icao,dest_icao,n_voos,freq_cancelamento,freq_chuva_10mm"


def _booking(origin="SBGR", dest="SBFI", date="2026-09-10") -> BookingInput:
    return BookingInput.model_validate(
        {
            "booking_id": "BK-T",
            "flight_date": date,
            "origin_icao": origin,
            "dest_icao": dest,
            "ticket_value_brl": 1200.0,
            "accommodation_value_brl": 600.0,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "Foz", "start": date, "end": date},
        }
    )


def _table(tmp_path: Path, rows: list[str]) -> ExposureTable:
    csv = tmp_path / "exposure.csv"
    csv.write_text(EXPOSURE_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return ExposureTable(csv_path=csv)


def test_exact_lookup_has_metodo_fontes_and_version(tmp_path):
    table = _table(tmp_path, ["2026,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02"])
    result = PriceEngine(table=table).price(_booking())
    assert result.metodo == PricingMethod.DADOS_COMPLETOS
    assert result.aviso is None
    assert result.versao_nota_tecnica == TECH_NOTE_VERSION
    assert result.fontes and result.fontes[0].tipo == "exposicao"
    assert result.n_exposicao == 800
    assert result.sparsity_flag is False


def test_nearest_lookup_sets_aviso_and_sparsity(tmp_path):
    table = _table(tmp_path, ["2026,9,SBGR→SBFI,SBGR,SBFI,120,0.01,0.02"])
    result = PriceEngine(table=table).price(_booking(date="2026-10-10"))
    assert result.aviso is not None and "não exato" in result.aviso
    assert any(s.tipo == "fallback" for s in result.fontes)
    assert result.sparsity_flag is True  # n=120 < 500


def test_missing_route_uses_defaults(tmp_path):
    table = _table(tmp_path, ["2026,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02"])
    result = PriceEngine(table=table, use_interpolation=False).price(_booking(origin="SBXX", dest="ZZZZ"))
    assert "Sem exposição" in (result.aviso or "")
    assert any(s.ref == "defaults" for s in result.fontes)
    assert result.freq_cancel == PriceEngine.DEFAULT_FREQ_CANCEL
    assert result.sparsity_flag is True


@pytest.mark.parametrize(
    ("mm", "expected"),
    [(9.9, False), (10.0, False), (10.1, True), (10.000001, True), (0.0, False)],
)
def test_rain_trigger_frontier(mm, expected):
    assert rain_trigger(mm) is expected


def test_annex_i_reference_still_matches(tmp_path):
    table = _table(tmp_path, [])
    engine = PriceEngine(table=table)
    result = engine.price_from_rates(
        capital_insured=ANNEX_I_REFERENCE["capital_insured"],
        freq_cancel=ANNEX_I_REFERENCE["pure_rate"] / 2,
        freq_rain=ANNEX_I_REFERENCE["pure_rate"] / 2,
        loss_basis_brl=ANNEX_I_REFERENCE["capital_insured"],
    )
    assert result.pure_rate == pytest.approx(ANNEX_I_REFERENCE["pure_rate"], rel=1e-6)
    assert result.commercial_rate == pytest.approx(ANNEX_I_REFERENCE["commercial_rate"], rel=1e-5)
    assert result.premium_brl == pytest.approx(ANNEX_I_REFERENCE["premium_brl"], abs=0.02)
