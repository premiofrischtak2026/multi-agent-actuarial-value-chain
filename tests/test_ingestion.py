import json
from pathlib import Path

import pytest

from ingestion import FixtureMailboxSource, InMemoryMailboxSource, PdfTextExtractor, StubBookingExtractor
from ingestion.document_mapping import booking_from_document, is_booking_input
from ingestion.missing_fields import missing_fields
from ingestion.ports import Attachment, InboundEmail, MailboxSource, DocumentExtractor, BookingExtractor
from ingestion.service import ingest_email, ingest_next, save_artifacts

EMAILS_DIR = Path(__file__).resolve().parents[1] / "src" / "fixtures" / "backtest" / "emails"

DOC = {
    "message_id": "eml-test",
    "cliente": {
        "nome": "Ana Souza",
        "documento": "123.456.789-09",
        "consentimento_termos": True,
        "consentimento_privacidade": True,
    },
    "valor_voo": 1500.0,
    "hospedagem": 800.0,
    "origem": "SBGR",
    "destino": "SBFI",
    "data_inicio": "2026-09-10",
    "data_fim": "2026-09-15",
    "hotel": {"cidade": "Foz do Iguaçu", "diarias": 5, "diaria_contratada": 160.0},
}


def _json_email(doc: dict) -> InboundEmail:
    return InboundEmail(
        message_id=doc["message_id"],
        attachments=[Attachment("booking.json", "application/json", json.dumps(doc).encode())],
    )


def test_adapters_implement_ports():
    assert isinstance(FixtureMailboxSource(EMAILS_DIR), MailboxSource)
    assert isinstance(PdfTextExtractor(), DocumentExtractor)
    assert isinstance(StubBookingExtractor(), BookingExtractor)


def test_fixture_mailbox_is_idempotent():
    mailbox = FixtureMailboxSource(EMAILS_DIR)
    first = list(mailbox.poll())
    assert len(first) >= 1
    assert list(mailbox.poll()) == []


def test_ingest_json_email_ok():
    result = ingest_email(
        _json_email(DOC), document_extractor=PdfTextExtractor(), booking_extractor=StubBookingExtractor()
    )
    assert result.ok
    assert result.booking is not None
    assert result.booking.dest_icao == "SBFI"
    assert result.booking.accommodation_value_brl == 800.0
    assert result.booking.consents is not None and result.booking.consents.termos


def test_ingest_incomplete_email_reports_missing():
    partial = {"message_id": "x", "cliente": {"nome": "João"}, "origem": "SBGR"}
    result = ingest_email(
        _json_email(partial), document_extractor=PdfTextExtractor(), booking_extractor=StubBookingExtractor()
    )
    assert not result.ok
    assert result.booking is None
    assert "Destino (ICAO)" in result.missing
    assert "Hotel (diárias)" in result.missing


def test_ingest_pdf_email_end_to_end():
    data = (EMAILS_DIR / "booking_foz.pdf").read_bytes()
    email_message = InboundEmail(
        message_id="eml-pdf", attachments=[Attachment("booking_foz.pdf", "application/pdf", data)]
    )
    result = ingest_email(
        email_message, document_extractor=PdfTextExtractor(), booking_extractor=StubBookingExtractor()
    )
    assert result.ok
    assert result.booking is not None and result.booking.passenger.name == "Ana Souza"


def test_ingest_next_from_fixture_mailbox():
    mailbox = FixtureMailboxSource(EMAILS_DIR, patterns=["sample_booking.eml"])
    result = ingest_next(
        mailbox, document_extractor=PdfTextExtractor(), booking_extractor=StubBookingExtractor()
    )
    assert result is not None and result.ok


def test_document_mapping_and_passthrough():
    booking = booking_from_document(DOC, message_id="eml-1")
    assert booking.origin_icao == "SBGR"
    assert booking.hotel is not None and booking.hotel.diarias == 5
    assert is_booking_input({"booking_id": "b", "flight_date": "2026-01-01", "origin_icao": "A", "dest_icao": "B", "ticket_value_brl": 1})


def test_missing_fields_helper():
    assert missing_fields(DOC) == []
    assert "Valor do voo" in missing_fields({})


def test_save_artifacts(tmp_path):
    result = ingest_email(
        _json_email(DOC), document_extractor=PdfTextExtractor(), booking_extractor=StubBookingExtractor()
    )
    target = save_artifacts(result, tmp_path)
    assert (target / "email.json").exists()
    assert (target / "booking_raw.json").exists()
