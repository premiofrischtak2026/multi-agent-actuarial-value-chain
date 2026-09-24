import json
from pathlib import Path

from schemas import (
    AcceptanceCode,
    BookingInput,
    BookingFixture,
    HotelInfo,
    PolicyVersions,
    PricingMethod,
)

FIXTURES = Path(__file__).resolve().parents[1] / "src" / "fixtures" / "backtest" / "sample_bookings.json"


def _legacy_booking() -> dict:
    return {
        "booking_id": "BK-TEST-0001",
        "flight_date": "2026-09-10",
        "origin_icao": "SBGR",
        "dest_icao": "SBFI",
        "ticket_value_brl": 1500.0,
        "excursion_value_brl": 800.0,
        "passenger": {"name": "Ana Souza", "document": "123.456.789-09"},
        "stay": {"city": "Foz do Iguaçu", "start": "2026-09-10", "end": "2026-09-15"},
    }


def test_legacy_fixture_without_new_fields_validates():
    booking = BookingInput.model_validate(_legacy_booking())
    assert booking.message_id is None
    assert booking.consents is None
    assert booking.hotel is None
    # legacy excursion is treated as accommodation
    assert booking.accommodation_value_brl == 800.0


def test_all_sample_fixtures_still_validate():
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixtures = [BookingFixture.model_validate(item) for item in data]
    assert len(fixtures) > 0


def test_hotel_derives_accommodation_when_missing():
    payload = _legacy_booking()
    payload.pop("excursion_value_brl")
    payload["hotel"] = {"cidade": "Foz do Iguaçu", "diarias": 5, "diaria_contratada": 160.0}
    booking = BookingInput.model_validate(payload)
    assert booking.accommodation_value_brl == 800.0


def test_hotel_total():
    assert HotelInfo(cidade="Foz", diarias=5, diaria_contratada=160.0).total_brl == 800.0


def test_enums_and_versions():
    assert {m.value for m in PricingMethod} == {"dados_completos", "analogia"}
    assert {c.value for c in AcceptanceCode} == {"A", "AC", "RH", "R", "SI"}
    versions = PolicyVersions(nota_tecnica="NTA-001@v1.0", regras="AC-001@v1.0")
    assert versions.fontes == []
