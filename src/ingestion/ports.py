"""Ports (interfaces) for the ingestion layer.

They decouple the ingress channel / document handling from the rest of the
system, so the backtest can inject fixtures while production injects IMAP + LLM.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class InboundEmail:
    message_id: str
    sender: str = ""
    subject: str = ""
    attachments: list[Attachment] = field(default_factory=list)


@runtime_checkable
class MailboxSource(Protocol):
    def poll(self) -> Iterable[InboundEmail]:
        """Yield unprocessed inbound emails (read-only)."""
        ...


@runtime_checkable
class DocumentExtractor(Protocol):
    def extract(self, attachment: Attachment) -> str:
        """Return the plain text of a document attachment (e.g. PDF)."""
        ...


@runtime_checkable
class BookingExtractor(Protocol):
    def extract(self, text: str, *, message_id: str | None = None) -> dict:
        """Return a raw booking mapping (document schema) from text."""
        ...
