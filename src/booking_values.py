"""Helpers for trip value (capital insured and indemnifiable loss)."""

from __future__ import annotations

from schemas import BookingInput


def accommodation_brl(booking: BookingInput) -> float:
    """Accommodation amount; older fixtures may fall back to excursion_value_brl."""
    if booking.accommodation_value_brl > 0:
        return booking.accommodation_value_brl
    return booking.excursion_value_brl


def trip_loss_brl(booking: BookingInput) -> float:
    """Indemnifiable loss: flight ticket plus accommodation."""
    return booking.ticket_value_brl + accommodation_brl(booking)


def capital_insured_brl(booking: BookingInput) -> float:
    """Capital insured equals the indemnity base for this product."""
    return trip_loss_brl(booking)
