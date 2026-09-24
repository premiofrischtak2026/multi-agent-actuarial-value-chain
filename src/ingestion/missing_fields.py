"""Detect missing mandatory fields so the flow never quotes on partial data."""

from __future__ import annotations

from typing import Any

# Mandatory document fields (article Table 7). Dotted paths into the raw JSON.
REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("cliente.nome", "Passageiro (nome)"),
    ("cliente.documento", "Documento"),
    ("origem", "Origem (ICAO)"),
    ("destino", "Destino (ICAO)"),
    ("data_inicio", "Data de início"),
    ("data_fim", "Data de fim"),
    ("valor_voo", "Valor do voo"),
    ("hotel.cidade", "Hotel (cidade)"),
    ("hotel.diarias", "Hotel (diárias)"),
    ("hotel.diaria_contratada", "Hotel (diária contratada)"),
)


def _get(raw: dict[str, Any], path: str) -> Any:
    current: Any = raw
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def missing_fields(raw: dict[str, Any]) -> list[str]:
    """Human-readable list of missing/invalid mandatory fields."""
    missing: list[str] = []
    for path, label in REQUIRED_FIELDS:
        value = _get(raw, path)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(label)
    return missing
