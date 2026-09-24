export type PolicyRecord = {
  booking_id: string;
  policy_id: string | null;
  decision: "accepted" | "rejected";
  underwriting_reason: string;
  passenger_name: string;
  passenger_document: string;
  origin_icao: string;
  dest_icao: string;
  route: string;
  flight_date: string;
  stay_city: string;
  stay_start: string;
  stay_end: string;
  ticket_value_brl: number;
  accommodation_value_brl?: number;
  excursion_value_brl: number;
  capital_insured_brl: number;
  premium_brl: number;
  pure_premium_brl: number;
  issued_at: string | null;
  effective_start: string | null;
  effective_end: string | null;
  has_claim: boolean;
  claim_total_brl: number;
  claim_cancel_brl: number;
  claim_rain_brl: number;
  claim_reasons: string[];
};

export function formatBrl(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatDate(s: string | null) {
  if (!s) return "—";
  return new Date(s + (s.length === 10 ? "T12:00:00" : "")).toLocaleDateString("pt-BR");
}

type Props = {
  records: PolicyRecord[];
  filter: "all" | "accepted" | "rejected";
  onFilterChange: (f: "all" | "accepted" | "rejected") => void;
  search: string;
  onSearchChange: (s: string) => void;
};

export default function PoliciesTab({
  records,
  filter,
  onFilterChange,
  search,
  onSearchChange,
}: Props) {
  const q = search.trim().toLowerCase();
  const filtered = records.filter((r) => {
    if (filter !== "all" && r.decision !== filter) return false;
    if (!q) return true;
    return (
      r.booking_id.toLowerCase().includes(q) ||
      (r.policy_id ?? "").toLowerCase().includes(q) ||
      r.passenger_name.toLowerCase().includes(q) ||
      r.route.toLowerCase().includes(q) ||
      r.origin_icao.toLowerCase().includes(q) ||
      r.dest_icao.toLowerCase().includes(q)
    );
  });

  const accepted = records.filter((r) => r.decision === "accepted").length;
  const rejected = records.filter((r) => r.decision === "rejected").length;
  const withClaim = records.filter((r) => r.has_claim).length;

  return (
    <div className="policies-tab">
      <div className="policies-toolbar">
        <div className="policies-stats">
          <span>{records.length} processadas</span>
          <span className="sep">·</span>
          <span className="ok">{accepted} aceitas</span>
          <span className="sep">·</span>
          <span className="no">{rejected} recusadas</span>
          <span className="sep">·</span>
          <span className="claim">{withClaim} com sinistro</span>
        </div>
        <div className="policies-filters">
          <input
            placeholder="Buscar booking, apólice, passageiro, rota…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
          <select value={filter} onChange={(e) => onFilterChange(e.target.value as Props["filter"])}>
            <option value="all">Todas</option>
            <option value="accepted">Aceitas</option>
            <option value="rejected">Recusadas</option>
          </select>
        </div>
      </div>

      <div className="table-wrap">
        <table className="policies-table">
          <thead>
            <tr>
              <th>Decisão</th>
              <th>Booking / Apólice</th>
              <th>Passageiro</th>
              <th>Rota</th>
              <th>Voo</th>
              <th>Estadia</th>
              <th>Capital / Perda</th>
              <th>Prêmio</th>
              <th>Vigência</th>
              <th>Sinistro</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="empty">
                  {records.length === 0
                    ? "Nenhuma apólice ainda — inicie a simulação na aba Simulação."
                    : "Nenhum resultado para os filtros aplicados."}
                </td>
              </tr>
            )}
            {filtered.map((r) => (
              <tr
                key={r.booking_id}
                data-testid="policy-row"
                className={r.decision === "rejected" ? "row-rejected" : r.has_claim ? "row-claim" : ""}
              >
                <td>
                  <span className={`pill ${r.decision}`}>
                    {r.decision === "accepted" ? "Aceita" : "Recusada"}
                  </span>
                  {r.decision === "rejected" && (
                    <div className="sub muted" title={r.underwriting_reason}>
                      {r.underwriting_reason.slice(0, 48)}
                      {r.underwriting_reason.length > 48 ? "…" : ""}
                    </div>
                  )}
                </td>
                <td>
                  <div className="mono">{r.booking_id}</div>
                  <div className="sub muted">{r.policy_id ?? "—"}</div>
                </td>
                <td>
                  <div>{r.passenger_name}</div>
                  <div className="sub muted">{r.passenger_document}</div>
                </td>
                <td>
                  <div className="mono">{r.route}</div>
                  <div className="sub muted">
                    {r.origin_icao} → {r.dest_icao}
                  </div>
                </td>
                <td>
                  <div>{formatDate(r.flight_date)}</div>
                  <div className="sub muted">
                    voo {formatBrl(r.ticket_value_brl)}
                    {(r.accommodation_value_brl ?? 0) > 0 && ` + hosp. ${formatBrl(r.accommodation_value_brl!)}`}
                  </div>
                </td>
                <td>
                  <div>{r.stay_city}</div>
                  <div className="sub muted">
                    {formatDate(r.stay_start)} – {formatDate(r.stay_end)}
                  </div>
                </td>
                <td className="mono">
                  <div>{formatBrl(r.capital_insured_brl)}</div>
                  <div className="sub muted">voo + hospedagem</div>
                </td>
                <td className="mono">
                  <div>{formatBrl(r.premium_brl)}</div>
                  <div className="sub muted">PPR {formatBrl(r.pure_premium_brl)}</div>
                </td>
                <td>
                  {r.decision === "accepted" ? (
                    <>
                      <div className="sub">{formatDate(r.effective_start)} – {formatDate(r.effective_end)}</div>
                      <div className="sub muted">emitida {r.issued_at ? new Date(r.issued_at).toLocaleString("pt-BR") : "—"}</div>
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  {r.decision === "accepted" ? (
                    r.has_claim ? (
                      <>
                        <span className="pill claim">Sim</span>
                        <div className="mono claim-amt" data-testid="claim-amount">
                          {formatBrl(r.claim_total_brl)}
                        </div>
                        <div className="sub muted">
                          {r.claim_total_brl === r.capital_insured_brl
                            ? "voo + hospedagem"
                            : `capital ${formatBrl(r.capital_insured_brl)}`}
                        </div>
                        <div className="sub muted">
                          {r.claim_cancel_brl > 0 && `cancel. ${formatBrl(r.claim_cancel_brl)} `}
                          {r.claim_rain_brl > 0 && `chuva ${formatBrl(r.claim_rain_brl)}`}
                        </div>
                      </>
                    ) : (
                      <span className="pill none">Não</span>
                    )
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
