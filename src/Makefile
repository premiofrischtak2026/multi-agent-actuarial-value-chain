.PHONY: start data test help

PKG_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PROJECT_ROOT := $(abspath $(PKG_DIR)/..)
ROOT := $(abspath $(PROJECT_ROOT)/..)

# Bootstrap: baixa das fontes públicas (ANAC/OpenFlights/Open-Meteo) e reconstrói.
# Ver PLAN.md, Fase 0A. Use OFFLINE=--offline ou FORCE=--force.
data:
	cd $(PKG_DIR) && uv run --project $(PROJECT_ROOT) python -m main data sync $(OFFLINE) $(FORCE)

# Suíte de testes (pytest a partir da raiz do projeto).
test:
	cd $(PROJECT_ROOT) && uv run pytest

# API FastAPI + dashboard Vite (Ctrl+C encerra os dois).
start:
	$(PKG_DIR)/scripts/run_api_dashboard.sh

help:
	@echo "make data   — baixa das fontes públicas e reconstrói os dados"
	@echo "make test   — roda a suíte de testes"
	@echo "make start  — sobe a API FastAPI e o dashboard Vite"
