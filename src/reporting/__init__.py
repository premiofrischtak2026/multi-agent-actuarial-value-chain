"""Actuarial reporting / explainability."""

from reporting.dossier import build_dossier, render_markdown
from reporting.pdf import render_dossier_pdf

__all__ = ["build_dossier", "render_markdown", "render_dossier_pdf"]
