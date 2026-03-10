import { useState, useEffect, useRef } from "react";

const MAX_POINTS = 100;

// ── Metric configs ─────────────────────────────────────────────────────────────
// BANDWIDTH: higherBad:false → low BW = red (attack drops BW to 2-15 Mb/s)
// All others: higherBad:true → high value = red
const METRICS_CONFIG = [
  {
    key: "bandwidth",
    label: "NETWORK BANDWIDTH",
    unit: "Mb/s",
    max: 150,
    // Thresholds for LOW-is-bad:
    // critAt = below this → CRITICAL (attack: 2–15 Mb/s)
    // warnAt = below this → WARNING  (congestion: ~45 Mb/s)
    // above warnAt        → NOMINAL  (healthy: 80–120 Mb/s)
    warnAt: 45,
    critAt: 15,
    higherBad: false,
    goodColor: "#00ff88",
    warnColor: "#ffcc00",
    critColor: "#ff3333",
    bgColor:   "#061410",
    gridColor: "#0d2820",
    description: "Avg bandwidth — drops sharply during attack",
  },
  {
    key: "latency",
    label: "AVG LATENCY",
    unit: "ms",
    max: 500,
    warnAt: 60,
    critAt: 150,
    higherBad: true,
    goodColor: "#44ddff",
    warnColor: "#ffcc00",
    critColor: "#ff3333",
    bgColor:   "#061218",
    gridColor: "#0d2030",
    description: "Mean latency — spikes during attack/consensus",
  },
  {
    key: "packet_loss",
    label: "PACKET LOSS",
    unit: "%",
    max: 80,
    warnAt: 5,
    critAt: 20,
    higherBad: true,
    goodColor: "#ff8844",
    warnColor: "#ff5500",
    critColor: "#ff1111",
    bgColor:   "#180a06",
    gridColor: "#2a1408",
    description: "Dropped packet ratio — soars during DoS attack",
  },
  {
    key: "jitter",
    label: "JITTER",
    unit: "ms",
    max: 100,
    warnAt: 15,
    critAt: 45,
    higherBad: true,
    goodColor: "#ffee44",
    warnColor: "#ff9900",
    critColor: "#ff3333",
    bgColor:   "#161400",
    gridColor: "#262200",
    description: "Packet delivery variation — rises under load",
  },
  {
    key: "rtt",
    label: "ROUND-TRIP TIME",
    unit: "ms",
    max: 1000,
    warnAt: 120,
    critAt: 350,
    higherBad: true,
    goodColor: "#bb88ff",
    warnColor: "#ffcc00",
    critColor: "#ff3333",
    bgColor:   "#0e0816",
    gridColor: "#1a1028",
    description: "Average RTT — rises with latency during attack",
  },
];

function avg(edgeMetrics, key) {
  const vals = Object.values(edgeMetrics);
  if (!vals.length) return 0;
  return vals.reduce((s, e) => s + (e[key] ?? 0), 0) / vals.length;
}

// ── Color: respects higherBad direction ───────────────────────────────────────
function getLineColor(val, cfg) {
  if (cfg.higherBad) {
    // High value = bad
    if (val >= cfg.critAt) return cfg.critColor;
    if (val >= cfg.warnAt) return cfg.warnColor;
    return cfg.goodColor;
  } else {
    // Low value = bad (bandwidth)
    if (val <= cfg.critAt) return cfg.critColor;
    if (val <= cfg.warnAt) return cfg.warnColor;
    return cfg.goodColor;
  }
}

function getStatusLabel(val, cfg) {
  if (cfg.higherBad) {
    if (val >= cfg.critAt) return "CRITICAL";
    if (val >= cfg.warnAt) return "WARNING";
    return "NOMINAL";
  } else {
    if (val <= cfg.critAt) return "CRITICAL";
    if (val <= cfg.warnAt) return "WARNING";
    return "NOMINAL";
  }
}

// ── Canvas — zoomed dynamic Y so every fluctuation is visible ─────────────────
function drawCanvas(canvas, points, cfg) {
  if (!canvas || points.length < 2) return;

  const rect = canvas.getBoundingClientRect();
  const W = Math.floor(rect.width  || 400);
  const H = Math.floor(rect.height || 90);
  if (canvas.width !== W || canvas.height !== H) {
    canvas.width  = W;
    canvas.height = H;
  }
  const ctx = canvas.getContext("2d");

  // Dynamic Y: zoom into actual data range for visibility
  const rawMin = Math.min(...points);
  const rawMax = Math.max(...points);
  const spread = rawMax - rawMin;
  const pad    = Math.max(spread * 0.4, cfg.max * 0.04);
  const yMin   = Math.max(0,       rawMin - pad);
  const yMax   = Math.min(cfg.max, rawMax + pad);
  const yRange = yMax - yMin || 1;
  const toY    = v => H - 5 - ((Math.min(Math.max(v, yMin), yMax) - yMin) / yRange) * (H - 10);

  ctx.fillStyle = cfg.bgColor;
  ctx.fillRect(0, 0, W, H);

  // Grid lines
  ctx.strokeStyle = cfg.gridColor; ctx.lineWidth = 1;
  [0.25, 0.5, 0.75].forEach(p => {
    const y = Math.floor(H * p) + 0.5;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  });

  // Threshold lines — only render if inside visible range
  const drawT = (val, color) => {
    if (val < yMin || val > yMax) return;
    const y = Math.floor(toY(val)) + 0.5;
    ctx.save();
    ctx.strokeStyle = color; ctx.globalAlpha = 0.75;
    ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.restore();
  };
  drawT(cfg.warnAt, cfg.warnColor);
  drawT(cfg.critAt, cfg.critColor);

  const latest    = points[points.length - 1];
  const lineColor = getLineColor(latest, cfg);
  const coords    = points.map((v, i) => ({
    x: (i / (points.length - 1)) * (W - 8) + 4,
    y: toY(v),
  }));

  // Area fill
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, lineColor + "55");
  grad.addColorStop(1, lineColor + "00");
  ctx.beginPath();
  coords.forEach((c, i) => i === 0 ? ctx.moveTo(c.x, c.y) : ctx.lineTo(c.x, c.y));
  ctx.lineTo(coords[coords.length - 1].x, H);
  ctx.lineTo(coords[0].x, H);
  ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  // Glow stroke
  ctx.beginPath(); ctx.strokeStyle = lineColor; ctx.lineWidth = 3;
  ctx.lineJoin = "round"; ctx.shadowColor = lineColor; ctx.shadowBlur = 10;
  coords.forEach((c, i) => i === 0 ? ctx.moveTo(c.x, c.y) : ctx.lineTo(c.x, c.y));
  ctx.stroke(); ctx.shadowBlur = 0;

  // Crisp stroke
  ctx.beginPath(); ctx.lineWidth = 1.8;
  coords.forEach((c, i) => i === 0 ? ctx.moveTo(c.x, c.y) : ctx.lineTo(c.x, c.y));
  ctx.stroke();

  // Y-axis scale labels
  ctx.fillStyle = "#33445599"; ctx.font = "9px 'Courier New'";
  ctx.fillText(yMax.toFixed(0), 4, 12);
  ctx.fillText(yMin.toFixed(0), 4, H - 4);

  // Live dot
  const last = coords[coords.length - 1];
  ctx.beginPath(); ctx.arc(last.x, last.y, 5, 0, Math.PI * 2);
  ctx.fillStyle = "#fff"; ctx.shadowColor = lineColor; ctx.shadowBlur = 14;
  ctx.fill(); ctx.shadowBlur = 0;
  ctx.beginPath(); ctx.arc(last.x, last.y, 3, 0, Math.PI * 2);
  ctx.fillStyle = lineColor; ctx.fill();

  // Attack region highlight on right quarter when recently critical
  const recent    = points.slice(-Math.ceil(points.length * 0.25));
  const isCritical = cfg.higherBad
    ? Math.max(...recent) >= cfg.critAt
    : Math.min(...recent) <= cfg.critAt;

  if (isCritical) {
    const sx = coords[Math.floor(coords.length * 0.75)]?.x ?? W * 0.75;
    const hl = ctx.createLinearGradient(sx, 0, W, 0);
    hl.addColorStop(0, cfg.critColor + "00");
    hl.addColorStop(1, cfg.critColor + "28");
    ctx.fillStyle = hl;
    ctx.fillRect(sx, 0, W - sx, H);
  }
}

// ── Metric card ───────────────────────────────────────────────────────────────
function MetricCard({ cfg, points }) {
  const canvasRef = useRef(null);
  const latest    = points.length > 0 ? points[points.length - 1] : null;
  const valColor  = latest !== null ? getLineColor(latest, cfg) : "#2a5a7a";

  const minVal = points.length ? Math.min(...points) : 0;
  const maxVal = points.length ? Math.max(...points) : 0;
  const avgVal = points.length ? points.reduce((a, b) => a + b, 0) / points.length : 0;

  const statusLabel = latest !== null ? getStatusLabel(latest, cfg) : "NO DATA";
  const statusColor =
    statusLabel === "CRITICAL" ? cfg.critColor :
    statusLabel === "WARNING"  ? cfg.warnColor : cfg.goodColor;

  useEffect(() => {
    const id = requestAnimationFrame(() => drawCanvas(canvasRef.current, points, cfg));
    return () => cancelAnimationFrame(id);
  }, [points, cfg]);

  useEffect(() => {
    const ro = new ResizeObserver(() =>
      requestAnimationFrame(() => drawCanvas(canvasRef.current, points, cfg))
    );
    if (canvasRef.current) ro.observe(canvasRef.current);
    return () => ro.disconnect();
  }, [points, cfg]);

  // Direction hint shown in header
  const directionHint = cfg.higherBad ? "↓ lower = better" : "↑ higher = better";

  return (
    <div style={{
      background: "#060e18",
      border: `1px solid ${valColor}2a`,
      borderTop: `3px solid ${valColor}`,
      borderRadius: 10, padding: "14px 16px", marginBottom: 12,
      boxShadow: `0 0 30px ${valColor}0d`,
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: 0, right: 0, width: 200, height: 200,
        background: `radial-gradient(circle at top right, ${valColor}08, transparent 70%)`,
        pointerEvents: "none",
      }} />

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: "11px", fontWeight: 800, letterSpacing: "2.5px",
                        color: valColor, textShadow: `0 0 10px ${valColor}66` }}>
            {cfg.label}
          </div>
          <div style={{ fontSize: "9px", color: "#334455", letterSpacing: "1px", marginTop: 2 }}>
            {cfg.description}
          </div>
          <div style={{ fontSize: "9px", color: "#223344", letterSpacing: "1px", marginTop: 1 }}>
            {directionHint}
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: "26px", fontWeight: 900, color: valColor,
                        textShadow: `0 0 16px ${valColor}99`,
                        fontFamily: "'Courier New',monospace", lineHeight: 1 }}>
            {latest !== null ? latest.toFixed(1) : "--"}
            <span style={{ fontSize: "12px", fontWeight: 700, marginLeft: 4 }}>{cfg.unit}</span>
          </div>
          <div style={{ marginTop: 4, display: "inline-flex", alignItems: "center", gap: 5,
                        padding: "2px 8px", background: `${statusColor}18`,
                        border: `1px solid ${statusColor}44`, borderRadius: 20 }}>
            <div style={{ width: 5, height: 5, borderRadius: "50%",
                          background: statusColor, boxShadow: `0 0 6px ${statusColor}`,
                          animation: statusLabel !== "NOMINAL" ? "blink 0.8s infinite" : "none" }} />
            <span style={{ fontSize: "9px", fontWeight: 800, letterSpacing: "1.5px",
                           color: statusColor }}>
              {statusLabel}
            </span>
          </div>
        </div>
      </div>

      {/* Canvas */}
      <canvas ref={canvasRef} style={{
        width: "100%", height: "90px", display: "block",
        borderRadius: 6, border: `1px solid ${cfg.gridColor}`, marginBottom: 10,
      }} />

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr",
                    gap: 6, fontSize: "9px",
                    borderTop: `1px solid ${cfg.gridColor}`, paddingTop: 8 }}>
        {[
          ["MIN",  minVal.toFixed(1), null],
          ["AVG",  avgVal.toFixed(1), null],
          ["MAX",  maxVal.toFixed(1), null],
          // For bandwidth: WARN = drops below 45, CRIT = drops below 15
          // For others:    WARN = exceeds threshold, CRIT = exceeds threshold
          ["WARN", cfg.warnAt, cfg.warnColor],
          ["CRIT", cfg.critAt, cfg.critColor],
        ].map(([lbl, val, col]) => (
          <div key={lbl} style={{ textAlign: "center" }}>
            <div style={{ color: "#334455", letterSpacing: "1px", marginBottom: 2 }}>{lbl}</div>
            <div style={{ color: col ?? "#8899aa", fontWeight: 700,
                          fontFamily: "'Courier New',monospace" }}>
              {val}<span style={{ fontSize: "8px", opacity: 0.7 }}>{cfg.unit}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Network health banner ─────────────────────────────────────────────────────
function HealthBanner({ snapshot, phase }) {
  const phaseColor =
    phase === "attack"    ? "#ff4444" :
    phase === "consensus" ? "#cc88ff" : "#00ff88";
  const phaseLabel =
    phase === "attack"    ? "⚠ ATTACK DETECTED — METRICS DEGRADING" :
    phase === "consensus" ? "◈ PBFT CONSENSUS — LINKS SATURATED"    :
    "● NOMINAL — ALL LINKS HEALTHY";

  // Health score: penalise each metric proportionally
  let health = 100;
  if (snapshot) {
    METRICS_CONFIG.forEach(cfg => {
      const v = snapshot[cfg.key] ?? 0;
      let penalty;
      if (cfg.higherBad) {
        // Penalty grows as value approaches max
        penalty = Math.min(v / cfg.max, 1);
      } else {
        // Penalty grows as value falls toward 0
        penalty = 1 - Math.min(v / cfg.max, 1);
      }
      health -= penalty * (100 / METRICS_CONFIG.length);
    });
    health = Math.max(0, Math.round(health));
  }
  const healthColor = health > 70 ? "#00ff88" : health > 40 ? "#ffcc00" : "#ff3333";

  return (
    <div style={{ padding: "10px 14px", background: "#060f1e",
                  borderBottom: "1px solid #0d2137", flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "7px 12px", background: `${phaseColor}0d`,
                    border: `1px solid ${phaseColor}33`, borderRadius: 6, marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%",
                        background: phaseColor, boxShadow: `0 0 10px ${phaseColor}`,
                        animation: phase !== "idle" ? "blink 0.8s infinite" : "none" }} />
          <span style={{ fontSize: "10px", color: phaseColor, fontWeight: 800,
                         letterSpacing: "1.5px", textShadow: `0 0 8px ${phaseColor}66` }}>
            {phaseLabel}
          </span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: "8px", color: "#334455", letterSpacing: "1px" }}>NET HEALTH</div>
          <div style={{ fontSize: "18px", fontWeight: 900, color: healthColor,
                        textShadow: `0 0 10px ${healthColor}`,
                        fontFamily: "'Courier New',monospace", lineHeight: 1 }}>
            {health}<span style={{ fontSize: "10px" }}>%</span>
          </div>
        </div>
      </div>
      <div style={{ height: 4, background: "#0d2137", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${health}%`,
                      background: `linear-gradient(90deg,${healthColor}88,${healthColor})`,
                      borderRadius: 2, boxShadow: `0 0 8px ${healthColor}`,
                      transition: "width 0.4s ease, background 0.4s ease" }} />
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function MetricsGraphs({ edgeMetrics, phase }) {
  const [history,   setHistory]   = useState([]);
  const [activeTab, setActiveTab] = useState("all");

  useEffect(() => {
    if (!edgeMetrics || Object.keys(edgeMetrics).length === 0) return;
    const snap = {
      bandwidth:   avg(edgeMetrics, "bandwidth"),
      latency:     avg(edgeMetrics, "latency"),
      packet_loss: avg(edgeMetrics, "packet_loss"),
      jitter:      avg(edgeMetrics, "jitter"),
      rtt:         avg(edgeMetrics, "rtt"),
    };
    setHistory(prev => [...prev, snap].slice(-MAX_POINTS));
  }, [edgeMetrics]);

  const TABS = [
    { key: "all",         label: "ALL"     },
    { key: "bandwidth",   label: "BW"      },
    { key: "latency",     label: "LATENCY" },
    { key: "packet_loss", label: "LOSS"    },
    { key: "jitter",      label: "JITTER"  },
    { key: "rtt",         label: "RTT"     },
  ];

  const visibleMetrics =
    activeTab === "all" ? METRICS_CONFIG :
    METRICS_CONFIG.filter(m => m.key === activeTab);

  const latestSnap = history[history.length - 1] ?? null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%",
                  overflow: "hidden", fontFamily: "'Courier New',monospace",
                  background: "#050d1a" }}>

      <div style={{ padding: "12px 14px 0", background: "#060f1e",
                    borderBottom: "1px solid #0d2137", flexShrink: 0 }}>
        <div style={{ fontSize: "12px", color: "#44aacc", letterSpacing: "3px",
                      fontWeight: 800, marginBottom: 10, textShadow: "0 0 10px #44aacc66" }}>
          NETWORK-WIDE METRICS
        </div>
        <div style={{ display: "flex", gap: 4, marginBottom: 10, flexWrap: "wrap" }}>
          {TABS.map(({ key, label }) => (
            <button key={key} onClick={() => setActiveTab(key)} style={{
              padding: "5px 9px",
              background: activeTab === key ? "#1a3a55" : "#08141e",
              border: `1px solid ${activeTab === key ? "#44aacc" : "#0d2137"}`,
              borderRadius: 4,
              color: activeTab === key ? "#44ddff" : "#334455",
              fontSize: "10px", fontWeight: 700, letterSpacing: "1px",
              cursor: "pointer", fontFamily: "'Courier New',monospace",
              boxShadow: activeTab === key ? "0 0 8px #44aacc44" : "none",
              transition: "all 0.15s",
            }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <HealthBanner snapshot={latestSnap} phase={phase} />

      <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px",
                    background: "#050d1a" }}>
        {history.length < 2 ? (
          <div style={{ textAlign: "center", color: "#334455",
                        fontSize: "12px", marginTop: 40, letterSpacing: "2px" }}>
            AWAITING NETWORK DATA...
          </div>
        ) : (
          visibleMetrics.map(cfg => (
            <MetricCard
              key={cfg.key}
              cfg={cfg}
              points={history.map(h => h[cfg.key] ?? 0)}
            />
          ))
        )}
      </div>

      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }
        ::-webkit-scrollbar { width:4px }
        ::-webkit-scrollbar-track { background:#040d18 }
        ::-webkit-scrollbar-thumb { background:#1a3a55; border-radius:3px }
      `}</style>
    </div>
  );
}