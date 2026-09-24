"""Booking extractors implementing the ``BookingExtractor`` port.

``StubBookingExtractor`` is deterministic (parses JSON already present in the
text) and is used by the backtest. ``LLMBookingExtractor`` uses the configured
chat model (``llm.get_chat_model``) and never computes prices or decisions.
"""

from __future__ import annotations

import json
from typing import Any

DOCUMENT_SCHEMA_HINT = (
    "{"
    '"message_id": str, "cliente": {"nome": str, "documento": str, '
    '"consentimento_termos": bool, "consentimento_privacidade": bool}, '
    '"valor_voo": number, "hospedagem": number, "origem": str, "destino": str, '
    '"data_inicio": "YYYY-MM-DD", "data_fim": "YYYY-MM-DD", '
    '"hotel": {"cidade": str, "diarias": int, "categoria": str, "diaria_contratada": number}'
    "}"
)


def _find_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("Nenhum JSON de reserva encontrado no texto do documento")


class StubBookingExtractor:
    """Deterministic extractor: reads the JSON booking payload from the text."""

    def extract(self, text: str, *, message_id: str | None = None) -> dict[str, Any]:
        raw = _find_json(text)
        if message_id and not raw.get("message_id"):
            raw["message_id"] = message_id
        return raw


class LLMBookingExtractor:
    """LLM extractor: interprets the document and returns the document JSON."""

    def __init__(self, chat_model=None):
        self._chat_model = chat_model

    def _model(self):
        if self._chat_model is None:
            from llm import get_chat_model

            self._chat_model = get_chat_model()
        return self._chat_model

    def extract(self, text: str, *, message_id: str | None = None) -> dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = (
            "Extract the travel booking fields from the document below. "
            f"Return valid JSON only matching this schema: {DOCUMENT_SCHEMA_HINT}\n\n{text}"
        )
        response = self._model().invoke(
            [
                SystemMessage(content="You extract structured travel booking data."),
                HumanMessage(content=prompt),
            ]
        )
        raw = _find_json(str(response.content))
        if message_id and not raw.get("message_id"):
            raw["message_id"] = message_id
        return raw
