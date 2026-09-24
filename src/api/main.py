"""FastAPI API for backtest and dashboard."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.flow_docs import AGENT_FLOW
from backtest.engine import BacktestEngine
from backtest.fixtures import generate_fixtures
from config import FIXTURES_DIR
from data_sync import sync_data
from governance import review
from graph.workflow import run_flow
from monitoring.indicators import compute_indicators
from reporting import build_dossier, render_dossier_pdf
from schemas import FlowStep
from storage import ClaimBase, DossierBase, PolicyBase


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warn (do not block) when the heavy data artifacts are not built yet."""
    import logging

    from data_sync import missing_artifacts

    missing = missing_artifacts()
    if missing:
        logging.getLogger("uvicorn.error").warning(
            "Dados incompletos (%d artefatos ausentes). Rode `python -m main data sync` "
            "ou `make data`. O backtest segue com a golden sample.",
            len(missing),
        )
    yield


app = FastAPI(title="Travel Insurance PoC API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine = BacktestEngine()
_policy_base = PolicyBase()
_claim_base = ClaimBase()
_dossier_base = DossierBase()

FLOW_STEPS = [
    {"id": FlowStep.PURCHASE.value, "label": "Purchase"},
    {"id": FlowStep.PRICE.value, "label": "Pricing"},
    {"id": FlowStep.UNDERWRITE.value, "label": "Underwriting"},
    {"id": FlowStep.CRITERIA.value, "label": "Acceptance criteria"},
    {"id": FlowStep.ISSUE.value, "label": "Issuance"},
    {"id": FlowStep.MONITOR.value, "label": "Monitoring"},
    {"id": FlowStep.CLAIM.value, "label": "Claim"},
    {"id": FlowStep.END.value, "label": "End"},
]


class SimulationConfig(BaseModel):
    route_filter: str | None = None
    year_filter: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    delay_ms: float = 200
    speed: float = 1.0
    fixture_count: int | None = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "indemnity_model": "flight_plus_accommodation",
        "indemnity_description": "Claim = flight ticket + accommodation",
    }


@app.get("/api/flow")
def get_flow():
    return {"steps": FLOW_STEPS}


@app.get("/api/flow/agents")
def get_agent_flow():
    return AGENT_FLOW


@app.get("/api/fixtures")
def list_fixtures():
    path = FIXTURES_DIR / "sample_bookings.json"
    if not path.exists():
        generate_fixtures(n=200)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {"count": len(data), "path": str(path)}


@app.post("/api/fixtures/generate")
def create_fixtures(n: int = 200):
    fixtures = generate_fixtures(n=n)
    return {"generated": len(fixtures)}


@app.get("/api/fixtures/meta")
def fixtures_meta(
    route_filter: str | None = None,
    year_filter: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    if not (FIXTURES_DIR / "sample_bookings.json").exists():
        generate_fixtures(n=200)
    return _engine.count_matching(
        route_filter=route_filter,
        year_filter=year_filter,
        date_from=date_from,
        date_to=date_to,
    )


@app.post("/api/backtest/run")
def run_backtest_sync(config: SimulationConfig | None = None):
    config = config or SimulationConfig()
    if not (FIXTURES_DIR / "sample_bookings.json").exists():
        generate_fixtures(n=config.fixture_count or 200)
    results, metrics = _engine.run(
        route_filter=config.route_filter,
        year_filter=config.year_filter,
        date_from=config.date_from,
        date_to=config.date_to,
        limit=config.fixture_count,
    )
    return {"results_count": len(results), "metrics": metrics.model_dump()}


@app.get("/api/backtest/export")
def export_results():
    results, metrics = _engine.run()
    records = [r.model_dump(mode="json") for r in _engine.policy_records]
    return {"metrics": metrics.model_dump(), "results": results, "policy_records": records}


@app.post("/api/graph/run")
def run_graph_endpoint(booking: dict[str, Any], mode: str = "backtest", audit_gate: bool = False):
    state = run_flow(booking, mode=mode, audit_gate=audit_gate)
    policy = state.get("policy")
    if policy is not None:
        _policy_base.add(policy)
        try:
            dossier = build_dossier(
                booking=booking,
                pricing=state["pricing"],
                underwriting=state.get("underwriting"),
                acceptance=state.get("acceptance"),
                policy=policy,
                audit=state.get("audit") or review(state["pricing"], state.get("booking_model")),
            )
            _dossier_base.add(policy.policy_id, dossier)
        except Exception:  # noqa: BLE001 - persistence must not break the response
            pass
    claim = state.get("claim")
    if claim is not None and claim.sinistro_id:
        _claim_base.add(claim)
    return {
        "pricing": state.get("pricing").model_dump() if state.get("pricing") else None,
        "underwriting": state.get("underwriting").model_dump() if state.get("underwriting") else None,
        "acceptance": state.get("acceptance").model_dump(mode="json") if state.get("acceptance") else None,
        "policy": policy.model_dump(mode="json") if policy else None,
        "claim": claim.model_dump() if claim else None,
        "step_log": state.get("step_log", []),
    }


@app.post("/api/data/sync")
def data_sync(offline: bool = False, force: bool = False, year_start: int = 2016, year_end: int | None = None):
    report = sync_data(offline=offline, force=force, year_start=year_start, year_end=year_end)
    return report.__dict__


@app.get("/api/policies")
def list_policies():
    policies = _policy_base.all()
    return {"count": len(policies), "policies": policies}


@app.get("/api/claims")
def list_claims():
    claims = _claim_base.all()
    return {"count": len(claims), "claims": claims}


@app.get("/api/metrics")
def metrics():
    return compute_indicators(_engine.policy_records)


@app.get("/api/dossier/{policy_id}")
def get_dossier(policy_id: str):
    dossier = _dossier_base.get(policy_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossiê não encontrado")
    return dossier


@app.get("/api/dossier/{policy_id}/pdf")
def get_dossier_pdf(policy_id: str):
    dossier = _dossier_base.get(policy_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossiê não encontrado")
    pdf = render_dossier_pdf(dossier)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{policy_id}.pdf"'},
    )


@app.websocket("/ws/backtest")
async def backtest_websocket(websocket: WebSocket):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    sim_task: asyncio.Task | None = None
    relay_task: asyncio.Task | None = None

    async def relay():
        while True:
            event = await queue.get()
            if isinstance(event, dict):
                await websocket.send_json(event)
            else:
                await websocket.send_json(event.model_dump())

    relay_task = asyncio.create_task(relay())

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            cmd = msg.get("command")

            if cmd == "start":
                if sim_task and not sim_task.done():
                    _engine.stop()
                    sim_task.cancel()
                    try:
                        await sim_task
                    except asyncio.CancelledError:
                        pass

                config = SimulationConfig(**msg.get("config", {}))
                _engine.reset()
                _engine.set_speed(config.speed)
                if not (FIXTURES_DIR / "sample_bookings.json").exists():
                    generate_fixtures(n=config.fixture_count or 200)

                async def run_sim():
                    metrics = await _engine.run_streaming(
                        queue=queue,
                        delay_ms=config.delay_ms,
                        route_filter=config.route_filter,
                        year_filter=config.year_filter,
                        date_from=config.date_from,
                        date_to=config.date_to,
                        limit=config.fixture_count,
                    )
                    await queue.put({"type": "simulation_finished", "metrics": metrics.model_dump()})

                sim_task = asyncio.create_task(run_sim())

            elif cmd == "pause":
                _engine.pause()
            elif cmd == "resume":
                _engine.resume()
            elif cmd == "stop":
                _engine.stop()
                if sim_task and not sim_task.done():
                    sim_task.cancel()
            elif cmd == "speed":
                _engine.set_speed(float(msg.get("value", 1.0)))

    except WebSocketDisconnect:
        _engine.stop()
        if sim_task and not sim_task.done():
            sim_task.cancel()
        if relay_task and not relay_task.done():
            relay_task.cancel()


def main():
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
