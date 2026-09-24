import { useCallback, useEffect, useRef, useState } from "react";
import AgentsTab from "./AgentsTab";
import PoliciesTab, { PolicyRecord } from "./PoliciesTab";

type FlowStep = { id: string; label: string };

type Metrics = {
  policies_issued: number;
  policies_rejected: number;
  total_premium_brl: number;
  total_claims_brl: number;
  claims_with_payout: number;
  claims_without_payout: number;
  loss_ratio: number;
  combined_ratio: number;
  expected_pure_premium_brl: number;
  premium_vs_pure_ratio: number;
};

type StepEvent = {
  step: string;
  booking_id: string;
  timestamp: string;
  payload?: Record<string, unknown>;
};

const EMPTY_METRICS: Metrics = {
  policies_issued: 0,
  policies_rejected: 0,
  total_premium_brl: 0,
  total_claims_brl: 0,
  claims_with_payout: 0,
  claims_without_payout: 0,
  loss_ratio: 0,
  combined_ratio: 0,
  expected_pure_premium_brl: 0,
  premium_vs_pure_ratio: 0,
};

const STEP_ORDER = ["purchase", "price", "underwrite", "issue", "monitor", "claim", "end"];

function formatBrl(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatPct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

type TabId = "simulation" | "policies" | "agents";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("simulation");
  const [flowSteps, setFlowSteps] = useState<FlowStep[]>([]);
  const [currentStep, setCurrentStep] = useState<string>("");
  const [doneSteps, setDoneSteps] = useState<Set<string>>(new Set());
  const [events, setEvents] = useState<StepEvent[]>([]);
  const [policyRecords, setPolicyRecords] = useState<PolicyRecord[]>([]);
  const [policyFilter, setPolicyFilter] = useState<"all" | "accepted" | "rejected">("all");
  const [policySearch, setPolicySearch] = useState("");
  const [metrics, setMetrics] = useState<Metrics>(EMPTY_METRICS);
  const [status, setStatus] = useState<"idle" | "running" | "paused">("idle");
  const [speed, setSpeed] = useState(1);
  const [routeFilter, setRouteFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [fixtureMeta, setFixtureMeta] = useState<{
    total: number;
    matching: number;
    min_date: string | null;
    max_date: string | null;
  } | null>(null);
  const [currentBooking, setCurrentBooking] = useState<string>("");
  const [premiumSeries, setPremiumSeries] = useState<number[]>([]);
  const [claimsSeries, setClaimsSeries] = useState<number[]>([]);
  const [apiIndemnity, setApiIndemnity] = useState<string>("");
  const [selectedAgentStep, setSelectedAgentStep] = useState<string | null>("extract");
  const wsRef = useRef<WebSocket | null>(null);

  const refreshFixtureMeta = useCallback(async () => {
    const params = new URLSearchParams();
    if (routeFilter) params.set("route_filter", routeFilter);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    try {
      const res = await fetch(`/api/fixtures/meta?${params}`);
      const data = await res.json();
      setFixtureMeta(data);
    } catch {
      setFixtureMeta(null);
    }
  }, [routeFilter, dateFrom, dateTo]);

  useEffect(() => {
    fetch("/api/flow")
      .then((r) => r.json())
      .then((d) => setFlowSteps(d.steps));
    fetch("/api/fixtures")
      .then(() => refreshFixtureMeta())
      .catch(() => {});
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setApiIndemnity(d.indemnity_description ?? d.indemnity_model ?? ""))
      .catch(() => setApiIndemnity(""));
  }, [refreshFixtureMeta]);

  useEffect(() => {
    const t = setTimeout(refreshFixtureMeta, 300);
    return () => clearTimeout(t);
  }, [refreshFixtureMeta]);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const upsertPolicyRecord = useCallback((raw: PolicyRecord) => {
    setPolicyRecords((prev) => {
      const idx = prev.findIndex((r) => r.booking_id === raw.booking_id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = raw;
        return next;
      }
      return [raw, ...prev];
    });
  }, []);

  const handleStepEvent = useCallback((event: StepEvent) => {
    setEvents((prev) => [event, ...prev].slice(0, 200));
    setCurrentStep(event.step);
    setCurrentBooking(event.booking_id);
    setDoneSteps((prev) => {
      const next = new Set(prev);
      const idx = STEP_ORDER.indexOf(event.step);
      if (idx >= 0) STEP_ORDER.slice(0, idx).forEach((s) => next.add(s));
      return next;
    });
    if (event.step === "policy_record" && event.payload) {
      upsertPolicyRecord(event.payload as PolicyRecord);
    }
    if (event.step === "end" && event.payload?.record) {
      upsertPolicyRecord(event.payload.record as PolicyRecord);
    }
    if (event.step === "end" && event.payload?.metrics) {
      setMetrics(event.payload.metrics as Metrics);
    }
    if (event.step === "issue" && event.payload?.premium_brl) {
      setPremiumSeries((p) => [...p, event.payload!.premium_brl as number].slice(-60));
    }
    if (event.step === "claim" && event.payload?.total_paid_brl !== undefined) {
      setClaimsSeries((c) => [...c, event.payload!.total_paid_brl as number].slice(-60));
    }
  }, [upsertPolicyRecord]);

  const connect = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const ws = new WebSocket(`${proto}://${host}/ws/backtest`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === "complete" || data.type === "simulation_finished") {
        if (data.metrics) setMetrics(data.metrics);
        setStatus("idle");
        return;
      }
      handleStepEvent(data as StepEvent);
    };

    ws.onclose = () => setStatus("idle");
    return ws;
  }, [handleStepEvent]);

  const start = () => {
    setEvents([]);
    setDoneSteps(new Set());
    setPremiumSeries([]);
    setClaimsSeries([]);
    setPolicyRecords([]);
    setMetrics(EMPTY_METRICS);
    const ws = wsRef.current?.readyState === WebSocket.OPEN ? wsRef.current : connect();
    const hasDateFilter = Boolean(dateFrom || dateTo);
    const doStart = () => {
      send({
        command: "start",
        config: {
          delay_ms: 80,
          speed,
          fixture_count: hasDateFilter ? null : 30,
          route_filter: routeFilter || null,
          date_from: dateFrom || null,
          date_to: dateTo || null,
        },
      });
      setStatus("running");
    };
    if (ws.readyState === WebSocket.OPEN) doStart();
    else ws.addEventListener("open", doStart, { once: true });
  };

  const pause = () => {
    send({ command: "pause" });
    setStatus("paused");
  };

  const resume = () => {
    send({ command: "resume" });
    setStatus("running");
  };

  const stop = () => {
    send({ command: "stop" });
    setStatus("idle");
  };

  const exportResults = async () => {
    const res = await fetch("/api/backtest/export");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "backtest_export.json";
    a.click();
  };

  return (
    <div className="app">
      <header>
        <div>
          <h1>Seguro Viagem — Backtest PoC</h1>
          <p>
            Fluxo determinístico em tempo real · cancelamento + chuva &gt; 10mm
            {apiIndemnity && (
              <> · <strong>{apiIndemnity}</strong></>
            )}
          </p>
        </div>
        <span className={`status-badge ${status}`}>{status}</span>
      </header>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2>Controles</h2>
        <div className="controls">
          <button onClick={start} disabled={status === "running"}>▶ Play</button>
          <button className="secondary" onClick={pause} disabled={status !== "running"}>⏸ Pausar</button>
          <button className="secondary" onClick={resume} disabled={status !== "paused"}>▶ Retomar</button>
          <button className="secondary" onClick={stop}>⏹ Parar</button>
          <select value={speed} onChange={(e) => { setSpeed(Number(e.target.value)); send({ command: "speed", value: Number(e.target.value) }); }}>
            <option value={0.5}>0.5x</option>
            <option value={1}>1x</option>
            <option value={5}>5x</option>
            <option value={10}>10x</option>
            <option value={50}>Máximo</option>
          </select>
          <input placeholder="Filtro rota (ex: SBGR)" value={routeFilter} onChange={(e) => setRouteFilter(e.target.value)} />
          <button className="secondary" onClick={exportResults}>Exportar JSON</button>
        </div>
        <div className="date-controls">
          <label>
            <span>Data início</span>
            <input
              type="date"
              value={dateFrom}
              min={fixtureMeta?.min_date ?? undefined}
              max={dateTo || fixtureMeta?.max_date || undefined}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label>
            <span>Data fim</span>
            <input
              type="date"
              value={dateTo}
              min={dateFrom || fixtureMeta?.min_date || undefined}
              max={fixtureMeta?.max_date ?? undefined}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setDateFrom("");
              setDateTo("");
            }}
          >
            Limpar datas
          </button>
          {fixtureMeta && (
            <span className="date-meta">
              {fixtureMeta.matching} de {fixtureMeta.total} bookings no período
              {fixtureMeta.min_date && fixtureMeta.max_date && (
                <> · disponível {fixtureMeta.min_date} — {fixtureMeta.max_date}</>
              )}
            </span>
          )}
        </div>
      </div>

      <div className="tabs">
        <button
          type="button"
          className={`tab ${activeTab === "simulation" ? "active" : ""}`}
          onClick={() => setActiveTab("simulation")}
        >
          Simulação
        </button>
        <button
          type="button"
          className={`tab ${activeTab === "policies" ? "active" : ""}`}
          onClick={() => setActiveTab("policies")}
        >
          Apólices
          {policyRecords.length > 0 && <span className="tab-badge">{policyRecords.length}</span>}
        </button>
        <button
          type="button"
          className={`tab ${activeTab === "agents" ? "active" : ""}`}
          onClick={() => setActiveTab("agents")}
        >
          Agentes
        </button>
      </div>

      {activeTab === "agents" ? (
        <div className="panel agents-panel">
          <h2>Fluxo dos agentes (LangGraph)</h2>
          <AgentsTab selectedId={selectedAgentStep} onSelect={setSelectedAgentStep} />
        </div>
      ) : activeTab === "simulation" ? (
        <div className="grid">
          <div>
            <div className="panel" style={{ marginBottom: "1rem" }}>
              <h2>Fluxo do processo</h2>
              <div className="flow-steps">
                {flowSteps.map((s) => (
                  <div
                    key={s.id}
                    className={`flow-step ${currentStep === s.id ? "active" : ""} ${doneSteps.has(s.id) ? "done" : ""}`}
                  >
                    {s.label}
                  </div>
                ))}
              </div>
              {currentBooking && (
                <p style={{ marginTop: "1rem", fontSize: "0.85rem", color: "var(--muted)" }}>
                  Processando: <strong style={{ color: "var(--text)" }}>{currentBooking}</strong>
                </p>
              )}
            </div>

            <div className="panel">
              <h2>Métricas acumuladas</h2>
              <div className="metrics-grid">
                <div className="metric"><label>Apólices emitidas</label><strong>{metrics.policies_issued}</strong></div>
                <div className="metric"><label>Recusadas</label><strong>{metrics.policies_rejected}</strong></div>
                <div className="metric"><label>Prêmios</label><strong>{formatBrl(metrics.total_premium_brl)}</strong></div>
                <div className="metric"><label>Sinistros pagos</label><strong>{formatBrl(metrics.total_claims_brl)}</strong></div>
                <div className="metric"><label>Loss ratio</label><strong>{formatPct(metrics.loss_ratio)}</strong></div>
                <div className="metric"><label>Combined ratio</label><strong>{formatPct(metrics.combined_ratio)}</strong></div>
                <div className="metric"><label>Com sinistro</label><strong>{metrics.claims_with_payout}</strong></div>
                <div className="metric"><label>Sem sinistro</label><strong>{metrics.claims_without_payout}</strong></div>
                <div className="metric"><label>Prêmio / PPR</label><strong>{metrics.premium_vs_pure_ratio.toFixed(2)}x</strong></div>
              </div>
              <div style={{ marginTop: "1rem" }}>
                <label style={{ fontSize: "0.7rem", color: "var(--muted)" }}>Série prêmio (azul) vs sinistro (vermelho)</label>
                <div className="chart-bars">
                  {Array.from({ length: Math.max(premiumSeries.length, claimsSeries.length, 1) }).map((_, i) => {
                    const p = premiumSeries[i] ?? 0;
                    const c = claimsSeries[i] ?? 0;
                    const max = Math.max(...premiumSeries, ...claimsSeries, 1);
                    return (
                      <div key={i} style={{ flex: 1, display: "flex", gap: 1, alignItems: "flex-end", height: "100%" }}>
                        <div className="chart-bar" style={{ height: `${(p / max) * 100}%`, flex: 1 }} />
                        <div className="chart-bar claims" style={{ height: `${(c / max) * 100}%`, flex: 1 }} />
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="panel">
            <h2>Eventos em tempo real</h2>
            <div className="event-log">
              {events.length === 0 && <p style={{ color: "var(--muted)" }}>Aguardando simulação…</p>}
              {events.map((e, i) => (
                <div key={`${e.booking_id}-${e.step}-${i}`} className="event-item">
                  <span className="step">{e.step}</span>{" "}
                  <span className="booking">{e.booking_id}</span>
                  <pre style={{ margin: "0.25rem 0 0", whiteSpace: "pre-wrap", color: "var(--muted)" }}>
                    {JSON.stringify(e.payload, null, 0).slice(0, 280)}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="panel policies-panel">
          <h2>Apólices processadas</h2>
          <PoliciesTab
            records={policyRecords}
            filter={policyFilter}
            onFilterChange={setPolicyFilter}
            search={policySearch}
            onSearchChange={setPolicySearch}
          />
        </div>
      )}
    </div>
  );
}
