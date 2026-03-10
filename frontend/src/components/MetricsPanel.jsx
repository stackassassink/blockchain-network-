import { useState } from "react";

const EDGE_ORDER = [
  "N1-N2","N1-N3","N1-N4",
  "N2-N3","N2-N5",
  "N3-N6",
  "N4-N5","N4-N7",
  "N5-N6",
  "N6-N7",
];

// ── Color helpers — all respect the correct direction ─────────────────────────

function getLatencyColor(ms) {
  // HIGH latency = bad
  if (ms > 300) return "#ff3333";
  if (ms > 100) return "#ff9800";
  if (ms > 50)  return "#ffee00";
  return "#00ff88";
}

function getBwColor(bw) {
  // LOW bandwidth = bad (attack drops BW to 2-15 Mb/s)
  if (bw < 15)  return "#ff3333";   // CRITICAL — attack range
  if (bw < 45)  return "#ff9800";   // WARNING  — congested
  if (bw < 70)  return "#ffee00";   // CAUTION
  return "#00ff88";                  // NOMINAL  — healthy 80-120 Mb/s
}

function getJitterColor(j) {
  // HIGH jitter = bad
  if (j > 80) return "#ff3333";
  if (j > 30) return "#ff9800";
  if (j > 10) return "#ffee00";
  return "#00ff88";
}

function getLossColor(loss) {
  // HIGH packet loss = bad
  if (loss > 20) return "#ff3333";
  if (loss > 8)  return "#ff9800";
  if (loss > 2)  return "#ffee00";
  return "#00ff88";
}

function getHealthColor(h) {
  if (h > 80) return "#00ff88";
  if (h > 50) return "#ffee00";
  if (h > 25) return "#ff9800";
  return "#ff3333";
}

function Bar({ pct, color, height = 4 }) {
  return (
    <div style={{ width: "100%", height, background: "#0a1628",
                  borderRadius: 2, overflow: "hidden" }}>
      <div style={{
        height: "100%",
        width: `${Math.min(100, Math.max(0, pct))}%`,
        background: color,
        boxShadow: `0 0 6px ${color}88`,
        transition: "width 0.3s ease, background 0.3s ease",
        borderRadius: 2,
      }} />
    </div>
  );
}

function Metric({ label, value, color, barPct }) {
  return (
    <div style={{ background: "#07111e", border: "1px solid #0d2137",
                  borderRadius: 5, padding: "6px 8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "baseline", marginBottom: 4 }}>
        <span style={{ fontSize: "9px", color: "#2a6a8a",
                       fontWeight: 700, letterSpacing: "1.5px" }}>
          {label}
        </span>
        <span style={{ fontSize: "11px", color, fontWeight: 800,
                       textShadow: `0 0 8px ${color}66`,
                       transition: "color 0.3s" }}>
          {value}
        </span>
      </div>
      <Bar pct={barPct} color={color} />
    </div>
  );
}

function EdgeRow({ m, isActive }) {
  const healthColor = getHealthColor(m.health ?? 100);
  const latColor    = getLatencyColor(m.latency ?? 0);
  const bwColor     = getBwColor(m.bandwidth ?? 100);
  const jColor      = getJitterColor(m.jitter ?? 0);
  const lossColor   = getLossColor(m.packet_loss ?? 0);

  // Degraded = high latency OR high packet loss OR low bandwidth
  const isDegraded =
    (m.packet_loss ?? 0) > 8  ||
    (m.latency     ?? 0) > 100 ||
    (m.bandwidth   ?? 100) < 45;

  // BW bar: fill proportionally to current BW vs max (150)
  // Full bar = good (green), empty bar = bad (red/orange)
  const bwBarPct = Math.min(100, ((m.bandwidth ?? 0) / 150) * 100);

  return (
    <div style={{
      background: isDegraded ? "#120a06" : "#0a1424",
      border: `1px solid ${isDegraded ? "#ff980033" : "#0d2137"}`,
      borderLeft: `3px solid ${healthColor}`,
      borderRadius: 7, padding: "10px 12px",
      transition: "all 0.3s",
      opacity: isActive ? 1 : 0.55,
    }}>
      {/* Label + health */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: "12px", fontWeight: 800,
                       color: isActive ? "#44ccff" : "#2a5a7a",
                       letterSpacing: "0.5px" }}>
          {m.source} <span style={{ color: "#1a5a7a" }}>→</span> {m.target}
        </span>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {isDegraded && (
            <span style={{
              fontSize: "9px", color: "#ff9800",
              background: "#ff980018", border: "1px solid #ff980044",
              borderRadius: 3, padding: "1px 5px",
              fontWeight: 700, letterSpacing: "1px",
            }}>
              DEGRADED
            </span>
          )}
          <span style={{ fontSize: "10px", fontWeight: 800, color: healthColor,
                         textShadow: `0 0 6px ${healthColor}66` }}>
            {(m.health ?? 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* 2×2 metric grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 5 }}>
        <Metric
          label="LATENCY"
          value={`${(m.latency ?? 0).toFixed(1)}ms`}
          color={latColor}
          barPct={Math.min(100, ((m.latency ?? 0) / 500) * 100)}
        />
        <Metric
          label="RTT"
          value={`${(m.rtt ?? 0).toFixed(1)}ms`}
          color={latColor}
          barPct={Math.min(100, ((m.rtt ?? 0) / 1000) * 100)}
        />
        <Metric
          label="BANDWIDTH"
          value={`${(m.bandwidth ?? 0).toFixed(1)}Mb`}
          color={bwColor}
          barPct={bwBarPct}
        />
        <Metric
          label="JITTER"
          value={`${(m.jitter ?? 0).toFixed(1)}ms`}
          color={jColor}
          barPct={Math.min(100, ((m.jitter ?? 0) / 100) * 100)}
        />
      </div>

      {/* Packet loss — full width */}
      <div style={{ marginTop: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
          <span style={{ fontSize: "9px", color: "#2a6a8a",
                         fontWeight: 700, letterSpacing: "1.5px" }}>PACKET LOSS</span>
          <span style={{ fontSize: "11px", fontWeight: 800, color: lossColor,
                         textShadow: `0 0 6px ${lossColor}55` }}>
            {(m.packet_loss ?? 0).toFixed(1)}%
          </span>
        </div>
        <Bar pct={Math.min(100, ((m.packet_loss ?? 0) / 80) * 100)}
             color={lossColor} height={5} />
      </div>

      {/* Footer */}
      <div style={{ marginTop: 6, fontSize: "9px", color: "#1a4a6a", letterSpacing: "1px" }}>
        {m.message_count ?? 0} msgs · {
          (m.bytes_sent ?? 0) > 1048576
            ? `${(m.bytes_sent / 1048576).toFixed(1)}MB`
            : `${((m.bytes_sent ?? 0) / 1024).toFixed(0)}KB`
        } sent
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────
export default function MetricsPanel({ edgeMetrics, edges, phase }) {
  const [filter, setFilter] = useState("all");

  const activeEdgeKeys = new Set(
    (edges ?? []).filter(e => e.active).map(e => `${e.source}-${e.target}`)
  );

  const orderedMetrics = EDGE_ORDER
    .map(k => edgeMetrics[k])
    .filter(Boolean);

  const filtered = orderedMetrics.filter(m => {
    if (filter === "degraded")
      return (m.packet_loss ?? 0) > 5 ||
             (m.latency     ?? 0) > 80 ||
             (m.bandwidth   ?? 100) < 45;
    if (filter === "active") return activeEdgeKeys.has(m.edge_key);
    return true;
  });

  // Summary stats
  const n = orderedMetrics.length;
  const avgLatency = n
    ? (orderedMetrics.reduce((s, m) => s + (m.latency    ?? 0), 0) / n).toFixed(1)
    : "--";
  const avgBw = n
    ? (orderedMetrics.reduce((s, m) => s + (m.bandwidth  ?? 0), 0) / n).toFixed(1)
    : "--";
  const avgLoss = n
    ? (orderedMetrics.reduce((s, m) => s + (m.packet_loss?? 0), 0) / n).toFixed(1)
    : "--";
  const degradedCount = orderedMetrics.filter(
    m => (m.packet_loss ?? 0) > 5 ||
         (m.latency     ?? 0) > 80 ||
         (m.bandwidth   ?? 100) < 45
  ).length;

  const latNum  = parseFloat(avgLatency);
  const bwNum   = parseFloat(avgBw);
  const lossNum = parseFloat(avgLoss);

  const latColor  = latNum  > 150 ? "#ff3333" : latNum  > 60  ? "#ff9800" : "#00ff88";
  const bwColor   = bwNum   < 15  ? "#ff3333" : bwNum   < 45  ? "#ff9800" : "#00ff88";
  const lossColor = lossNum > 20  ? "#ff3333" : lossNum > 5   ? "#ff9800" : "#00ff88";
  const degColor  = degradedCount > 3 ? "#ff3333" : degradedCount > 0 ? "#ff9800" : "#00ff88";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%",
                  overflow: "hidden", fontFamily: "'Courier New',monospace" }}>

      {/* Header */}
      <div style={{ padding: "12px 14px 8px", borderBottom: "1px solid #0d2137",
                    flexShrink: 0 }}>
        <div style={{ fontSize: "11px", color: "#4a9aba", letterSpacing: "3px",
                      fontWeight: 700, marginBottom: 8 }}>
          NETWORK METRICS
        </div>

        {/* Summary row */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr",
                      gap: 5, marginBottom: 8 }}>
          {[
            { label: "AVG LAT",  value: `${avgLatency}ms`, color: latColor  },
            { label: "AVG BW",   value: `${avgBw}Mb`,      color: bwColor   },
            { label: "AVG LOSS", value: `${avgLoss}%`,     color: lossColor },
            { label: "DEGRADED", value: degradedCount,     color: degColor  },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: "#060f1e", border: "1px solid #0d2137",
                                      borderRadius: 5, padding: "6px 4px", textAlign: "center" }}>
              <div style={{ fontSize: "14px", fontWeight: 800, color,
                            textShadow: `0 0 8px ${color}66`, lineHeight: 1 }}>
                {value}
              </div>
              <div style={{ fontSize: "8px", color: "#2a5a7a", letterSpacing: "1.5px",
                            marginTop: 3, fontWeight: 700 }}>
                {label}
              </div>
            </div>
          ))}
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {[
            { key: "all",      label: "ALL EDGES" },
            { key: "active",   label: "ACTIVE" },
            { key: "degraded", label: `DEGRADED${degradedCount > 0 ? ` (${degradedCount})` : ""}` },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => setFilter(key)} style={{
              flex: 1, padding: "5px 4px",
              background: filter === key ? "#0d2a40" : "#060f1e",
              border: `1px solid ${filter === key ? "#44ccff66" : "#0d2137"}`,
              borderRadius: 4,
              color: filter === key ? "#44ccff" : "#2a5a7a",
              fontSize: "9px", fontWeight: 700, letterSpacing: "1px",
              cursor: "pointer", transition: "all 0.15s",
              fontFamily: "'Courier New',monospace",
            }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Edge list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "10px 12px",
                    display: "flex", flexDirection: "column", gap: 7 }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", color: "#1a4a6a",
                        fontSize: "11px", marginTop: 20 }}>
            {Object.keys(edgeMetrics).length === 0
              ? "Waiting for metrics..."
              : "No edges match filter"}
          </div>
        ) : (
          filtered.map(m => (
            <EdgeRow
              key={m.edge_key}
              m={m}
              isActive={activeEdgeKeys.has(m.edge_key)}
            />
          ))
        )}
      </div>

      {/* Phase banner */}
      {phase !== "idle" && (
        <div style={{
          padding: "8px 14px", borderTop: "1px solid #0d2137",
          background: phase === "attack"    ? "#1a0808" :
                      phase === "consensus" ? "#0d0818" : "#060f1e",
          flexShrink: 0,
        }}>
          <div style={{
            fontSize: "10px",
            color: phase === "attack"    ? "#ff4444" :
                   phase === "consensus" ? "#cc88ff" : "#44ccff",
            fontWeight: 700, letterSpacing: "2px", textAlign: "center",
          }}>
            {phase === "attack"    ? "⚡ BANDWIDTH COLLAPSED — ATTACK ACTIVE"  :
             phase === "consensus" ? "🔐 PBFT BROADCAST SATURATING LINKS"      :
             "⟳ RECOVERING"}
          </div>
        </div>
      )}
    </div>
  );
}