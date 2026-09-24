#!/usr/bin/env python3
"""Generate the e-mail/PDF ingestion fixtures (deterministic, for tests/demo)."""

from __future__ import annotations

import io
import json
from email.message import EmailMessage
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from paths import PACKAGE_DIR

OUT_DIR = PACKAGE_DIR / "fixtures" / "backtest" / "emails"

PAYLOAD = {
    "message_id": "eml-2026-0910-0041",
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
    "hotel": {
        "cidade": "Foz do Iguaçu",
        "diarias": 5,
        "categoria": "3 estrelas",
        "diaria_contratada": 160.0,
    },
}

INCOMPLETE = {
    "message_id": "eml-2026-0910-0099",
    "cliente": {"nome": "João", "documento": "111"},
    "valor_voo": 900.0,
    "origem": "SBGR",
    "data_inicio": "2026-10-01",
}


def _pdf_bytes(payload: dict) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    for line in json.dumps(payload, ensure_ascii=False, indent=2).splitlines():
        pdf.drawString(40, y, line)
        y -= 14
    pdf.save()
    return buffer.getvalue()


def _email(message_id: str, subject: str, attachment_name: str, subtype: str, data: bytes) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = message_id
    message["From"] = "cliente@example.com"
    message["Subject"] = subject
    message.set_content("Comprovantes em anexo.")
    message.add_attachment(data, maintype="application", subtype=subtype, filename=attachment_name)
    return message.as_bytes()


def main(argv: list[str] | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload_json = json.dumps(PAYLOAD, ensure_ascii=False).encode("utf-8")
    pdf_data = _pdf_bytes(PAYLOAD)
    incomplete_json = json.dumps(INCOMPLETE, ensure_ascii=False).encode("utf-8")

    (OUT_DIR / "booking_foz.pdf").write_bytes(pdf_data)
    (OUT_DIR / "sample_booking.eml").write_bytes(
        _email(PAYLOAD["message_id"], "Comprovantes da viagem", "booking.json", "json", payload_json)
    )
    (OUT_DIR / "sample_booking_pdf.eml").write_bytes(
        _email("eml-2026-0910-0042", "Comprovante PDF", "booking_foz.pdf", "pdf", pdf_data)
    )
    (OUT_DIR / "incomplete_booking.eml").write_bytes(
        _email(INCOMPLETE["message_id"], "Reserva incompleta", "booking.json", "json", incomplete_json)
    )
    print("Wrote fixtures in", OUT_DIR)


if __name__ == "__main__":
    main()
