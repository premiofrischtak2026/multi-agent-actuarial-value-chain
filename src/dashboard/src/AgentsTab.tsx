import { useEffect, useState } from "react";

export type AgentStep = {
  id: string;
  backtest_step: string;
  label: string;
  agent: string;
  icon: string;
  summary: string;
  inputs: string[];
  outputs: string[];
  logic: string[];
  formulas: string[];
  rules: string[];
  module: string;
  next: string[];
  branches?: Record<string, string>;
  also_emits?: string;
};

export type AgentFlow = {
  title: string;
  description: string;
  modes: Record<string, string>;
  steps: AgentStep[];
  graph_edges: { from: string; to: string; condition?: string }[];
};

const ICONS: Record<string, string> = {
  inbox: "📥",
  calculator: "🧮",
  shield: "🛡️",
  file: "📄",
  radar: "📡",
  flag: "🏁",
};

function StepIcon({ icon }: { icon: string }) {
  return <span className="agent-step-icon">{ICONS[icon] ?? "⚙️"}</span>;
}

type Props = {
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export default function AgentsTab({ selectedId, onSelect }: Props) {
  const [flow, setFlow] = useState<AgentFlow | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/flow/agents")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setFlow)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return <p className="agents-error">Não foi possível carregar o fluxo de agentes: {error}</p>;
  }

  if (!flow) {
    return <p className="agents-loading">Carregando fluxo de agentes…</p>;
  }

  const selected = flow.steps.find((s) => s.id === selectedId) ?? flow.steps[0];
  const stepById = Object.fromEntries(flow.steps.map((s) => [s.id, s]));

  return (
    <div className="agents-tab">
      <div className="agents-intro">
        <p>{flow.description}</p>
        <div className="agents-modes">
          {Object.entries(flow.modes).map(([mode, desc]) => (
            <span key={mode} className="agents-mode-pill">
              <strong>{mode}</strong> — {desc}
            </span>
          ))}
        </div>
      </div>

      <div className="agents-layout">
        <div className="agents-flow-panel">
          <h3>Fluxo LangGraph</h3>
          <p className="agents-hint">Clique em uma etapa para ver a lógica</p>
          <div className="agents-pipeline">
            {flow.steps.map((step, i) => {
              const isSelected = selected?.id === step.id;
              const hasBranch = step.branches && Object.keys(step.branches).length > 0;
              return (
                <div key={step.id} className="agents-pipeline-item">
                  <button
                    type="button"
                    className={`agent-node ${isSelected ? "selected" : ""}`}
                    onClick={() => onSelect(step.id)}
                    aria-pressed={isSelected}
                  >
                    <StepIcon icon={step.icon} />
                    <span className="agent-node-label">{step.label}</span>
                    <span className="agent-node-fn">{step.agent}</span>
                  </button>
                  {i < flow.steps.length - 1 && !hasBranch && (
                    <span className="agents-arrow" aria-hidden>→</span>
                  )}
                  {hasBranch && (
                    <div className="agents-branches">
                      {Object.entries(step.branches!).map(([target, label]) => (
                        <div key={target} className="agents-branch">
                          <span className="agents-branch-label">{label}</span>
                          <span className="agents-arrow">→</span>
                          <button
                            type="button"
                            className={`agent-node small ${selectedId === target ? "selected" : ""}`}
                            onClick={() => onSelect(target)}
                          >
                            {stepById[target]?.label ?? target}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <details className="agents-edges">
            <summary>Arestas do grafo</summary>
            <ul>
              {flow.graph_edges.map((e, i) => (
                <li key={i}>
                  <code>{e.from}</code> → <code>{e.to}</code>
                  {e.condition && <span className="muted"> ({e.condition})</span>}
                </li>
              ))}
            </ul>
          </details>
        </div>

        {selected && (
          <div className="agents-detail-panel">
            <header className="agents-detail-header">
              <StepIcon icon={selected.icon} />
              <div>
                <h3>{selected.label}</h3>
                <p className="agent-fn">{selected.agent}</p>
              </div>
            </header>

            <p className="agents-summary">{selected.summary}</p>

            <div className="agents-detail-grid">
              <section>
                <h4>Entradas</h4>
                <ul>
                  {selected.inputs.map((x) => (
                    <li key={x}><code>{x}</code></li>
                  ))}
                </ul>
              </section>
              <section>
                <h4>Saídas</h4>
                <ul>
                  {selected.outputs.map((x) => (
                    <li key={x}><code>{x}</code></li>
                  ))}
                </ul>
              </section>
            </div>

            {selected.logic.length > 0 && (
              <section className="agents-section">
                <h4>Lógica</h4>
                <ol>
                  {selected.logic.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ol>
              </section>
            )}

            {selected.formulas.length > 0 && (
              <section className="agents-section">
                <h4>Fórmulas</h4>
                <ul className="agents-formulas">
                  {selected.formulas.map((f, i) => (
                    <li key={i}><code>{f}</code></li>
                  ))}
                </ul>
              </section>
            )}

            {selected.rules.length > 0 && (
              <section className="agents-section">
                <h4>Regras / limites</h4>
                <ul>
                  {selected.rules.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </section>
            )}

            <footer className="agents-detail-footer">
              <div>
                <span className="muted">Módulo</span>
                <code>{selected.module}</code>
              </div>
              <div>
                <span className="muted">Etapa no backtest</span>
                <code>{selected.backtest_step}</code>
              </div>
              {selected.also_emits && (
                <div>
                  <span className="muted">Eventos extras</span>
                  <code>{selected.also_emits}</code>
                </div>
              )}
              {selected.next.length > 0 && (
                <div>
                  <span className="muted">Próximo(s)</span>
                  <span>
                    {selected.next.map((n) => (
                      <button
                        key={n}
                        type="button"
                        className="agent-link"
                        onClick={() => onSelect(n)}
                      >
                        {stepById[n]?.label ?? n}
                      </button>
                    ))}
                  </span>
                </div>
              )}
            </footer>
          </div>
        )}
      </div>
    </div>
  );
}
