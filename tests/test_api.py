from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

COMPLETE_BOOKING = {
    "booking_id": "BK-API-1",
    "flight_date": "2030-09-10",
    "origin_icao": "SBSP",
    "dest_icao": "SBBR",
    "ticket_value_brl": 1200,
    "accommodation_value_brl": 600,
    "passenger": {"name": "Ana", "document": "12345678909"},
    "stay": {"city": "Brasília", "start": "2030-09-10", "end": "2030-09-12"},
    "consents": {"termos": True, "privacidade": True},
    "hotel": {"cidade": "Brasília", "diarias": 2, "diaria_contratada": 150},
    "mediana_comparaveis": 145,
    "alta_temporada": True,
    "voucher_no_nome": True,
    "malha_elegivel": True,
    "fonte_indice": "Open-Meteo",
    "indice_cobre_janela": True,
    "fallback_contratado": True,
}


def test_health():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"


def test_graph_run_persists_policy_and_dossier():
    response = client.post("/api/graph/run", json=COMPLETE_BOOKING)
    assert response.status_code == 200
    data = response.json()
    assert data["pricing"] is not None
    assert data["acceptance"] is not None

    if data["policy"] is not None:
        policy_id = data["policy"]["policy_id"]
        assert client.get(f"/api/dossier/{policy_id}").status_code == 200
        pdf = client.get(f"/api/dossier/{policy_id}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
        policies = client.get("/api/policies").json()
        assert policies["count"] >= 1
        assert any(p["policy_id"] == policy_id for p in policies["policies"])


def test_dossier_404():
    assert client.get("/api/dossier/POL-NOPE").status_code == 404


def test_data_sync_offline_endpoint():
    body = client.post("/api/data/sync", params={"offline": "true"}).json()
    assert body["offline"] is True


def test_metrics_endpoint():
    body = client.get("/api/metrics").json()
    assert "n" in body
