from governance import review
from graph.workflow import run_flow
from pricing.engine import PriceEngine
from pricing.tables import ExposureTable
from reporting import build_dossier, render_markdown
from schemas import BookingInput

HEADER = "year,month,rota,origin_icao,dest_icao,n_voos,freq_cancelamento,freq_chuva_10mm"

COMPLETE_BOOKING = {
    "booking_id": "BK-D",
    "flight_date": "2030-09-10",
    "origin_icao": "SBGR",
    "dest_icao": "SBFI",
    "ticket_value_brl": 1500,
    "accommodation_value_brl": 800,
    "passenger": {"name": "Ana", "document": "12345678909"},
    "stay": {"city": "Foz do Iguaçu", "start": "2030-09-10", "end": "2030-09-15"},
    "consents": {"termos": True, "privacidade": True},
    "hotel": {"cidade": "Foz do Iguaçu", "diarias": 5, "diaria_contratada": 160},
    "mediana_comparaveis": 148,
    "alta_temporada": True,
    "voucher_no_nome": True,
    "malha_elegivel": True,
    "fonte_indice": "Open-Meteo",
    "indice_cobre_janela": True,
    "fallback_contratado": True,
}


def test_dossier_sections_and_entregaveis():
    state = run_flow(COMPLETE_BOOKING)
    dossier = build_dossier(
        booking=COMPLETE_BOOKING,
        pricing=state["pricing"],
        underwriting=state["underwriting"],
        acceptance=state["acceptance"],
        policy=state["policy"],
        audit=review(state["pricing"], state["booking_model"]),
    )
    assert set(dossier) >= {
        "cabecalho",
        "versoes",
        "mapa_variaveis",
        "localidades_referencia",
        "credibilidade",
        "sparsity",
        "decomposicao_pp_pc",
        "criterios",
        "pendencias",
        "auditoria",
        "regulatorio",
        "entregaveis",
    }
    assert len(dossier["entregaveis"]) == 5
    assert dossier["decomposicao_pp_pc"]
    assert dossier["criterios"]["veredito"] == "A"


def test_render_markdown_contains_sections():
    state = run_flow(COMPLETE_BOOKING)
    dossier = build_dossier(booking=COMPLETE_BOOKING, pricing=state["pricing"], acceptance=state["acceptance"])
    md = render_markdown(dossier)
    assert "Dossiê atuarial" in md
    assert "Decomposição PP" in md
    assert "Critérios de aceitação" in md


def test_dossier_lists_idw_localities(tmp_path):
    csv = tmp_path / "exposure.csv"
    csv.write_text(
        HEADER
        + "\n2025,9,SBGR→SBFI,SBGR,SBFI,800,0.01,0.02\n2025,9,SBGR→SBCT,SBGR,SBCT,600,0.02,0.03\n",
        encoding="utf-8",
    )
    table = ExposureTable(csv_path=csv)
    booking = BookingInput.model_validate(
        {
            "booking_id": "BK-IDW",
            "flight_date": "2025-09-10",
            "origin_icao": "SBGR",
            "dest_icao": "SBPA",
            "ticket_value_brl": 1000,
            "passenger": {"name": "Ana", "document": "1"},
            "stay": {"city": "Porto Alegre", "start": "2025-09-10", "end": "2025-09-12"},
        }
    )
    pricing = PriceEngine(table=table).price(booking)
    dossier = build_dossier(booking=booking.model_dump(mode="json"), pricing=pricing)
    assert dossier["localidades_referencia"]
    assert dossier["credibilidade"]["limiar"] == 500.0
