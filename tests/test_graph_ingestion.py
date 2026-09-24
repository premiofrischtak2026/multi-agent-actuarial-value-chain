from pathlib import Path

from graph.workflow import run_flow
from ingestion import FixtureMailboxSource, PdfTextExtractor, StubBookingExtractor

EMAILS_DIR = Path(__file__).resolve().parents[1] / "src" / "fixtures" / "backtest" / "emails"


def _mailbox(pattern: str) -> FixtureMailboxSource:
    return FixtureMailboxSource(EMAILS_DIR, patterns=[pattern])


def test_graph_runs_from_email_fixture():
    state = run_flow(
        mailbox=_mailbox("sample_booking.eml"),
        document_extractor=PdfTextExtractor(),
        booking_extractor=StubBookingExtractor(),
    )
    assert state["booking_model"] is not None
    assert state.get("pricing") is not None
    steps = [entry["step"] for entry in state["step_log"]]
    assert steps[0] == "extract"
    assert "price" in steps


def test_graph_stops_on_missing_fields():
    state = run_flow(
        mailbox=_mailbox("incomplete_booking.eml"),
        document_extractor=PdfTextExtractor(),
        booking_extractor=StubBookingExtractor(),
    )
    assert state.get("error") == "missing_fields"
    assert state.get("missing_fields")
    assert state.get("pricing") is None
    assert "Destino (ICAO)" in state["missing_fields"]


def test_graph_stops_on_empty_mailbox():
    state = run_flow(
        mailbox=FixtureMailboxSource(EMAILS_DIR, patterns=["does_not_exist.eml"]),
        document_extractor=PdfTextExtractor(),
        booking_extractor=StubBookingExtractor(),
    )
    assert state.get("error") == "mailbox_empty"
    assert state.get("pricing") is None


def test_graph_persists_artifacts_when_dir_given(tmp_path):
    run_flow(
        mailbox=_mailbox("sample_booking.eml"),
        document_extractor=PdfTextExtractor(),
        booking_extractor=StubBookingExtractor(),
        artifact_dir=tmp_path,
    )
    saved = list(tmp_path.glob("*/email.json"))
    assert saved, "ingestion artifacts should be persisted"
