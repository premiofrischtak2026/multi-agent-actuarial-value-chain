from graph.workflow import run_flow
from reporting import build_dossier, render_dossier_pdf

BOOKING = {
    "booking_id": "BK-PDF",
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


def test_render_dossier_pdf(tmp_path):
    state = run_flow(BOOKING)
    dossier = build_dossier(
        booking=BOOKING,
        pricing=state["pricing"],
        underwriting=state.get("underwriting"),
        acceptance=state.get("acceptance"),
        policy=state.get("policy"),
    )
    target = tmp_path / "dossier.pdf"
    data = render_dossier_pdf(dossier, target)
    assert data.startswith(b"%PDF")
    assert target.exists() and target.stat().st_size > 0
