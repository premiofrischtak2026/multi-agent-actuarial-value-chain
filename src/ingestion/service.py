"""Ingestion service: email -> attachments -> text -> booking -> BookingInput."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ingestion.document_mapping import booking_from_document
from ingestion.missing_fields import missing_fields
from ingestion.ports import Attachment, BookingExtractor, DocumentExtractor, InboundEmail, MailboxSource
from schemas import BookingInput


@dataclass
class IngestResult:
    email: InboundEmail
    raw: dict[str, Any] | None
    text: str
    missing: list[str] = field(default_factory=list)
    booking: BookingInput | None = None

    @property
    def ok(self) -> bool:
        return self.booking is not None and not self.missing


def _attachment_text(attachment: Attachment, document_extractor: DocumentExtractor) -> str:
    content_type = attachment.content_type.lower()
    filename = attachment.filename.lower()
    if "pdf" in content_type or filename.endswith(".pdf"):
        return document_extractor.extract(attachment)
    return attachment.data.decode("utf-8", errors="replace")


def ingest_email(
    email_message: InboundEmail,
    *,
    document_extractor: DocumentExtractor,
    booking_extractor: BookingExtractor,
) -> IngestResult:
    texts = [_attachment_text(att, document_extractor) for att in email_message.attachments]
    text = "\n".join(t for t in texts if t).strip()
    if not text:
        return IngestResult(
            email=email_message, raw=None, text="", missing=["Anexo (PDF/JSON ausente ou ilegível)"]
        )

    raw = booking_extractor.extract(text, message_id=email_message.message_id)
    missing = missing_fields(raw)
    booking = None
    if not missing:
        booking = booking_from_document(raw, message_id=email_message.message_id)
    return IngestResult(email=email_message, raw=raw, text=text, missing=missing, booking=booking)


def ingest_next(
    mailbox: MailboxSource,
    *,
    document_extractor: DocumentExtractor,
    booking_extractor: BookingExtractor,
) -> IngestResult | None:
    """Ingest the first unprocessed email, or None when the mailbox is empty."""
    for email_message in mailbox.poll():
        return ingest_email(
            email_message,
            document_extractor=document_extractor,
            booking_extractor=booking_extractor,
        )
    return None


def save_artifacts(result: IngestResult, out_dir: Path) -> Path:
    """Persist the email metadata, extracted text and raw JSON for audit."""
    target = Path(out_dir) / (result.email.message_id or "sem-id")
    target.mkdir(parents=True, exist_ok=True)
    (target / "email.json").write_text(
        json.dumps(
            {
                "message_id": result.email.message_id,
                "sender": result.email.sender,
                "subject": result.email.subject,
                "attachments": [a.filename for a in result.email.attachments],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (target / "extracted.txt").write_text(result.text, encoding="utf-8")
    if result.raw is not None:
        (target / "booking_raw.json").write_text(
            json.dumps(result.raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if result.missing:
        (target / "missing_fields.json").write_text(
            json.dumps(result.missing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return target
