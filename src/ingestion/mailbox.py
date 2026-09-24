"""Mailbox adapters implementing the ``MailboxSource`` port.

``FixtureMailboxSource`` / ``LocalDirMailboxSource`` read ``.eml`` files (no
network). ``ImapMailboxSource`` is the production channel and is the only one
that touches the network.
"""

from __future__ import annotations

import email
from collections.abc import Iterable, Sequence
from email.message import Message
from email.policy import default as default_policy
from imaplib import IMAP4_SSL
from pathlib import Path

from ingestion.ports import Attachment, InboundEmail


def _message_to_email(raw: bytes) -> InboundEmail:
    message: Message = email.message_from_bytes(raw, policy=default_policy)
    attachments: list[Attachment] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            Attachment(filename=filename, content_type=part.get_content_type(), data=payload)
        )
    return InboundEmail(
        message_id=message.get("Message-ID", "") or "",
        sender=message.get("From", "") or "",
        subject=message.get("Subject", "") or "",
        attachments=attachments,
    )


class FixtureMailboxSource:
    """Reads ``.eml`` files from a directory. Idempotent by Message-ID."""

    def __init__(self, directory: Path | str, patterns: Sequence[str] = ("*.eml",)):
        self.directory = Path(directory)
        self.patterns = patterns
        self.seen: set[str] = set()
        self._cache: list[InboundEmail] | None = None

    def _load(self) -> list[InboundEmail]:
        if self._cache is not None:
            return self._cache
        emails: list[InboundEmail] = []
        for pattern in self.patterns:
            for path in sorted(self.directory.glob(pattern)):
                inbound = _message_to_email(path.read_bytes())
                if not inbound.message_id:
                    inbound = InboundEmail(
                        message_id=path.stem,
                        sender=inbound.sender,
                        subject=inbound.subject,
                        attachments=inbound.attachments,
                    )
                emails.append(inbound)
        self._cache = emails
        return emails

    def poll(self) -> Iterable[InboundEmail]:
        fresh = [e for e in self._load() if e.message_id not in self.seen]
        self.seen.update(e.message_id for e in fresh)
        return fresh


class LocalDirMailboxSource(FixtureMailboxSource):
    """Development alias: same ``.eml`` directory reader, different intent."""


class InMemoryMailboxSource:
    """In-memory mailbox used by tests and the backtest."""

    def __init__(self, emails: Sequence[InboundEmail] | None = None):
        self._emails = list(emails or [])
        self.seen: set[str] = set()

    def add(self, inbound: InboundEmail) -> None:
        self._emails.append(inbound)

    def poll(self) -> Iterable[InboundEmail]:
        fresh = [e for e in self._emails if e.message_id not in self.seen]
        self.seen.update(e.message_id for e in fresh)
        return fresh


class ImapMailboxSource:
    """Production IMAP channel. Read-only: only ``UNSEEN`` messages are fetched."""

    def __init__(self, host: str, user: str, password: str, mailbox: str = "INBOX", port: int = 993):
        self.host = host
        self.user = user
        self.password = password
        self.mailbox = mailbox
        self.port = port
        self.seen: set[str] = set()

    def poll(self) -> Iterable[InboundEmail]:
        with IMAP4_SSL(self.host, self.port) as client:
            client.login(self.user, self.password)
            client.select(self.mailbox)
            status, data = client.search(None, "UNSEEN")
            if status != "OK":
                return []
            results: list[InboundEmail] = []
            for num in data[0].split():
                status, fetched = client.fetch(num, "(RFC822)")
                if status != "OK" or not fetched:
                    continue
                raw = fetched[0][1]
                if not isinstance(raw, bytes):
                    continue
                inbound = _message_to_email(raw)
                if inbound.message_id and inbound.message_id in self.seen:
                    continue
                self.seen.add(inbound.message_id)
                results.append(inbound)
            return results
