"""Acceptance criteria base types and context (article section 04)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from config import RULES_VERSION
from schemas import CriterionResult, CriterionStatus
from underwriting.portfolio import Portfolio


@dataclass
class AcceptanceContext:
    reference_date: date
    politica: str = "v1.0"
    versao_regras: str = RULES_VERSION
    portfolio: Portfolio | None = None


def pass_(codigo: str, evidencia: str) -> CriterionResult:
    return CriterionResult(codigo=codigo, resultado=CriterionStatus.PASS, evidencia=evidencia)


def deny(codigo: str, evidencia: str) -> CriterionResult:
    return CriterionResult(codigo=codigo, resultado=CriterionStatus.DENY, evidencia=evidencia)


def review(codigo: str, evidencia: str) -> CriterionResult:
    return CriterionResult(codigo=codigo, resultado=CriterionStatus.REVIEW, evidencia=evidencia)


def info(codigo: str, evidencia: str) -> CriterionResult:
    return CriterionResult(codigo=codigo, resultado=CriterionStatus.INFO, evidencia=evidencia)


def condition(codigo: str, evidencia: str) -> CriterionResult:
    """Accepted with conditions (AC): fixable by a documented product adjustment."""
    return CriterionResult(codigo=codigo, resultado=CriterionStatus.CONDITIONAL, evidencia=evidencia)
