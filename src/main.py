"""CLI for manual testing and utilities."""

from __future__ import annotations

from datetime import date
import argparse
import json
from pathlib import Path

from backtest.engine import BacktestEngine
from backtest.fixtures import generate_fixtures
from config import FIXTURES_DIR
from data_sync import sync_data
from graph.workflow import run_flow


def cmd_fixtures(args: argparse.Namespace) -> None:
    fixtures = generate_fixtures(n=args.n, output_dir=Path(args.output) if args.output else None)
    print(f"Generated {len(fixtures)} fixtures")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def cmd_backtest(args: argparse.Namespace) -> None:
    engine = BacktestEngine()
    path = Path(args.input) if args.input else FIXTURES_DIR / "sample_bookings.json"
    if not path.exists():
        generate_fixtures()
    fixtures = engine.load_fixtures(path)
    results, metrics = engine.run(
        fixtures,
        route_filter=args.route,
        year_filter=args.year,
        date_from=_parse_date(args.date_from),
        date_to=_parse_date(args.date_to),
    )
    print(json.dumps(metrics.model_dump(), indent=2, ensure_ascii=False))
    if args.output:
        Path(args.output).write_text(
            json.dumps({"metrics": metrics.model_dump(), "results": results}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def cmd_run(args: argparse.Namespace) -> None:
    path = Path(args.input)
    booking = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(booking, list):
        booking = booking[0]
    state = run_flow(booking, mode=args.mode)
    out = {
        "pricing": state.get("pricing").model_dump() if state.get("pricing") else None,
        "underwriting": state.get("underwriting").model_dump() if state.get("underwriting") else None,
        "policy": state.get("policy").model_dump(mode="json") if state.get("policy") else None,
        "claim": state.get("claim").model_dump() if state.get("claim") else None,
        "step_log": state.get("step_log", []),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


def cmd_data(args: argparse.Namespace) -> None:
    report = sync_data(
        offline=args.offline,
        force=args.force,
        year_start=args.year_start,
        year_end=args.year_end,
    )
    print(json.dumps(report.__dict__, indent=2, ensure_ascii=False))


def cmd_demo(args: argparse.Namespace) -> None:
    import subprocess
    import sys

    app = Path(__file__).resolve().parent / "app" / "fluxo.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.headless=true",
        "--server.port",
        str(args.port),
    ]
    raise SystemExit(subprocess.call(cmd))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Travel Insurance PoC CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fix = sub.add_parser("fixtures", help="Generate backtest fixtures")
    p_fix.add_argument("-n", type=int, default=200)
    p_fix.add_argument("-o", "--output", default=None)
    p_fix.set_defaults(func=cmd_fixtures)

    p_bt = sub.add_parser("backtest", help="Run deterministic backtest")
    p_bt.add_argument("-i", "--input", default=None)
    p_bt.add_argument("-o", "--output", default=None)
    p_bt.add_argument("--route", default=None)
    p_bt.add_argument("--year", type=int, default=None)
    p_bt.add_argument("--date-from", dest="date_from", default=None, help="YYYY-MM-DD")
    p_bt.add_argument("--date-to", dest="date_to", default=None, help="YYYY-MM-DD")
    p_bt.set_defaults(func=cmd_backtest)

    p_run = sub.add_parser("run", help="Run the LangGraph flow on a booking JSON file")
    p_run.add_argument("input", help="Booking JSON file")
    p_run.add_argument("--mode", choices=["backtest", "manual"], default="backtest")
    p_run.set_defaults(func=cmd_run)

    p_data = sub.add_parser("data", help="Data bootstrap from public sources")
    p_data.add_argument("action", nargs="?", choices=["sync"], default="sync")
    p_data.add_argument("--offline", action="store_true", help="Never touch the network")
    p_data.add_argument("--force", action="store_true", help="Rebuild even if artifacts exist")
    p_data.add_argument("--year-start", dest="year_start", type=int, default=2016)
    p_data.add_argument("--year-end", dest="year_end", type=int, default=None)
    p_data.set_defaults(func=cmd_data)

    p_srv = sub.add_parser("serve", help="Start the FastAPI server")
    p_srv.add_argument("--host", default="0.0.0.0")
    p_srv.add_argument("--port", type=int, default=8000)
    p_srv.add_argument("--reload", action="store_true")
    p_srv.set_defaults(func=cmd_serve)

    p_demo = sub.add_parser("demo", help="Open the Streamlit walkthrough of one booking")
    p_demo.add_argument("--port", type=int, default=8501)
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
