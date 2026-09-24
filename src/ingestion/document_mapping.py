"""Map the document schema (Portuguese, article Table 8) to ``BookingInput``."""

from __future__ import annotations

import re
from typing import Any

from schemas import BookingInput

_BOOKING_INPUT_KEYS = {"booking_id", "flight_date", "origin_icao", "dest_icao", "ticket_value_brl"}


def is_booking_input(raw: dict[str, Any]) -> bool:
    """True when the mapping already looks like a BookingInput payload."""
    return _BOOKING_INPUT_KEYS.issubset(raw.keys())


def _booking_id(raw: dict[str, Any], message_id: str | None) -> str:
    existing = str(raw.get("booking_id") or "").strip()
    if existing:
        return existing
    source = message_id or str(raw.get("message_id") or "sem-id")
    return "BK-" + re.sub(r"[^A-Za-z0-9]+", "-", source).strip("-")


def booking_from_document(raw: dict[str, Any], *, message_id: str | None = None) -> BookingInput:
    """Convert the article's document JSON into a validated BookingInput."""
    if is_booking_input(raw):
        payload = dict(raw)
        if message_id and not payload.get("message_id"):
            payload["message_id"] = message_id
        return BookingInput.model_validate(payload)

    cliente = raw.get("cliente") or {}
    hotel = raw.get("hotel") or {}
    destino = raw.get("destino")
    cidade = hotel.get("cidade") or destino or ""

    payload: dict[str, Any] = {
        "booking_id": _booking_id(raw, message_id),
        "message_id": message_id or raw.get("message_id"),
        "flight_date": raw.get("data_inicio"),
        "origin_icao": raw.get("origem"),
        "dest_icao": destino,
        "ticket_value_brl": raw.get("valor_voo"),
        "accommodation_value_brl": raw.get("hospedagem", 0.0),
        "passenger": {"name": cliente.get("nome"), "document": cliente.get("documento")},
        "stay": {"city": cidade, "start": raw.get("data_inicio"), "end": raw.get("data_fim")},
        "consents": {
            "termos": bool(cliente.get("consentimento_termos")),
            "privacidade": bool(cliente.get("consentimento_privacidade")),
        },
    }
    if hotel:
        payload["hotel"] = {
            "cidade": hotel.get("cidade") or cidade,
            "diarias": hotel.get("diarias", 0),
            "categoria": hotel.get("categoria"),
            "diaria_contratada": hotel.get("diaria_contratada", 0.0),
        }
    return BookingInput.model_validate(payload)
