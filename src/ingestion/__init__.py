"""Ingestion layer: mailbox -> document -> BookingInput (email/PDF channel)."""

from ingestion.extraction_agent import LLMBookingExtractor, StubBookingExtractor
from ingestion.mailbox import (
    FixtureMailboxSource,
    ImapMailboxSource,
    InMemoryMailboxSource,
    LocalDirMailboxSource,
)
from ingestion.pdf_extractor import PdfTextExtractor
from ingestion.ports import Attachment, InboundEmail, MailboxSource
from ingestion.service import IngestResult, ingest_email, ingest_next, save_artifacts

__all__ = [
    "Attachment",
    "InboundEmail",
    "MailboxSource",
    "FixtureMailboxSource",
    "LocalDirMailboxSource",
    "InMemoryMailboxSource",
    "ImapMailboxSource",
    "PdfTextExtractor",
    "StubBookingExtractor",
    "LLMBookingExtractor",
    "IngestResult",
    "ingest_email",
    "ingest_next",
    "save_artifacts",
]
