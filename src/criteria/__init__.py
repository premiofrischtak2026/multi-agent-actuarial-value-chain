"""Acceptance criteria package (article section 04)."""

from criteria.base import AcceptanceContext
from criteria.checks import CHECKS
from criteria.verdict import evaluate_acceptance, verdict_from_checks

__all__ = [
    "AcceptanceContext",
    "CHECKS",
    "evaluate_acceptance",
    "verdict_from_checks",
]
