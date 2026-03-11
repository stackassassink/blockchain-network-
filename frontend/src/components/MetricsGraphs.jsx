/**
 * MetricsGraphs.jsx — Fixed v3
 *
 * ROOT CAUSE FIXES:
 *  1. avg() now computes a WEIGHTED average — near-attack edges contribute
 *     more weight so spikes aren't diluted by 7 idle edges.
 *  2. Bandwidth graph Y-axis INVERTED: low BW draws HIGH on canvas so a
 *     DoS attack is visually a spike upward (not a drop nobody notices).
 *  3. Dynamic Y-axis: each graph auto-scales to [min(history), max(history)]
 *     with a padding factor — attack spikes fill the graph, not just 5%.
 *  4. Phase overlay: red/purple shading on graph background during attack/consensus.
 *  5. "SPIKE DETECTED" badge when current value crosses warn/crit threshold.
 */

import { useState, useEffect, useRef } from "react";

const MAX_POINTS = 80;

// ── Metric config ─────────────────────────────────────────────────────────────
const METRICS_CONFIG = [
  {
    key: "bandwidth",
    label: "NETWORK BANDWIDTH",
    unit: "Mb/s",
    baselineMin: 60,
    baselineMax: 140,
    higherBad: false,      // LOW bandwidth = bad
    warnAt: 45,            // warn if drops below this
    critAt: 15,            // crit if drops below this
    goodColor: "#00ff88",
    warnColor: "#ffcc00",
    critColor: "#ff3333",
    bgColor:   "#061410",
    gridColor: "#0d2820",
    description: "Drops during DoS (queue saturation), spikes briefly at flood start",
    invertY: true,         // draw low-BW as HIGH on graph so attack = visible spike
  },
  {
    key: "latency",
    label: "AVG LATENCY",
    unit: "ms",
    baselineMin: 8,
    baselineMax: 60,
    higherBad: true,
    warnAt: 80,
    critAt: 200,
    goodColor: "#44ddff",
    warnColor: "#ffcc00",
    critColor: "#ff3333",
    bgColor:   "#061218",
    gridColor: "#0d2030",
    description: "Spikes sharply during attack — queue saturation",
    invertY: false,
  },
  {
    key: "packet_loss",
    label: "PACKET LOSS",
    unit: "%",
    baselineMin: 0,
    baselineMax: 5,
    higherBad: true,
    warnAt: 8,
    critAt: 25,
    goodColor: "#ff8844",
    warnColor: "#ff5500",
    critColor: "#ff1111",
    bgColor:   "#180a06",
    gridColor: "#2a1408",
    description: "Soars during DoS (buffer overflow)",
    invertY: false,
  },
  {
    key: "jitter",
    label: "JITTER",
    unit: "ms",
    baselineMin: 1,
    baselineMax: 10,
    higherBad: true,
    warnAt: 20,
    critAt: 60,
    goodColor: "#ffee44",
    warnColor: "#ff9900",
    critColor: "#ff3333",
    bgColor:   "#161400",
    gridColor: "#262200",
    description: "Packet timing variance — rises under attack load",
    invertY: false,
  },
  {
    key: "rtt",
    label: "ROUND-TRIP TIME",
    unit: "ms",
    baselineMin: 16,
    baselineMax: 100,
    higherBad: true,
    warnAt: 150,
    critAt: 400,
    goodColor: "#bb88ff",
    warnColor: "#ffcc00",
    critColor: "#ff3333",
    bgColor:   "#0e0816",
    gridColor: "#1a1028",
    description: "Doubles with latency — rises sharply during attack",
    invertY: false,
  },
];

// ── Weighted average ──────────────────────────────────────────────────────────
// Edges near the attack get 4× weight so the spike shows in averages.
// We detect "attack edges" as those with extremely degraded metrics.
function weightedAvg(edgeMetrics, key, isHigherBad) {
  const vals = Object.values(edgeMetrics);
  if (!vals.length) return 0;

  const allVals = vals.map(e => e[key] ?? 0);
  const globalMedian = [...allVals].sort((a, b) => a - b)[Math.floor(allVals.length / 2)];

  let sumW = 0, sumV = 0;
  for (const v of allVals) {
    // Weight = 4 if this is clearly an outlier (attack edge), else 1
    const isOutlier = isHigherBad
      ? v > globalMedian * 2.5
      : v < globalMedian * 0.4;
    const w = isOutlier ? 4 : 1;
    sumW += w;
    sumV += w * v;
  }
  return sumV / sumW;
}

// ── Canvas sparkline ──────────────────────────────────────────────────────────
function Sparkline({ history, cfg, phase }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || history.length < 2) return;
    const ctx    = canvas.getContext("2d");
    const W      = canvas.width;
    const H      = canvas.height;

    // Dynamic Y range: auto-scale to data with 15% padding
    const rawVals = history.map(h => h[cfg.key] ?? 0);
    let dataMin = Math.min(...rawVals);
    let dataMax = Math.max(...rawVals);

    // Always show at least the baseline range so idle graphs aren't flat lines
    dataMin = Math.min(dataMin, cfg.baselineMin);
    dataMax = Math.max(dataMax, cfg.baselineMax);

    const pad   = (dataMax - dataMin) * 0.15;
    const yMin  = Math.max(0, dataMin - pad);
    const yMax  = dataMax + pad;
    const yRange = yMax - yMin || 1;

    const toY = (v) => {
      const norm = (v - yMin) / yRange;
      // invertY: low value → high on canvas (visually = spike for bandwidth drop)
      return cfg.invertY ? H * norm : H * (1 - norm);
    };

    // ── Background ────────────────────────────────────────────────────────
    ctx.fillStyle = cfg.bgColor;
    ctx.fillRect(0, 0, W, H);

    // Phase background tint
    if (phase === "attack") {
      ctx.fillStyle = "rgba(255,50,50,0.07)";
      ctx.fillRect(0, 0, W, H);
    } else if (phase === "consensus") {
      ctx.fillStyle = "rgba(180,100,255,0.07)";
      ctx.fillRect(0, 0, W, H);
    }

    // ── Grid lines ─────────────────────────────────────────────────────────
    ctx.strokeStyle = cfg.gridColor;
    ctx.lineWidth   = 0.5;
    for (let i = 1; i < 4; i++) {
      const y = (H / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    }

    // ── Threshold line ─────────────────────────────────────────────────────
    if (cfg.higherBad && cfg.critAt <= yMax) {
      const ty = toY(cfg.critAt);
      ctx.strokeStyle = cfg.critColor + "55";
      ctx.lineWidth   = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, ty);
      ctx.lineTo(W, ty);
      ctx.stroke();
      ctx.setLineDash([]);
    } else if (!cfg.higherBad && cfg.warnAt >= yMin) {
      const ty = toY(cfg.warnAt);
      ctx.strokeStyle = cfg.warnColor + "55";
      ctx.lineWidth   = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, ty);
      ctx.lineTo(W, ty);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // ── Area fill ──────────────────────────────────────────────────────────
    const pts = history.map((h, i) => ({
      x: (i / (history.length - 1)) * W,
      y: toY(h[cfg.key] ?? 0),
    }));

    const currentVal = rawVals[rawVals.length - 1];
    const lineColor  = getColor(cfg, currentVal);

    ctx.beginPath();
    ctx.moveTo(pts[0].x, H);
    ctx.lineTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      const cp = {
        x: (pts[i - 1].x + pts[i].x) / 2,
        y: (pts[i - 1].y + pts[i].y) / 2,
      };
      ctx.quadraticCurveTo(pts[i - 1].x, pts[i - 1].y, cp.x, cp.y);
    }
    ctx.lineTo(pts[pts.length - 1].x, pts[pts.length - 1].y);
    ctx.lineTo(pts[pts.length - 1].x, H);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, lineColor + "55");
    grad.addColorStop(1, lineColor + "08");
    ctx.fillStyle = grad;
    ctx.fill();

    // ── Line ──────────────────────────────────────────────────────────────
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      const cp = {
        x: (pts[i - 1].x + pts[i].x) / 2,
        y: (pts[i - 1].y + pts[i].y) / 2,
      };
      ctx.quadraticCurveTo(pts[i - 1].x, pts[i - 1].y, cp.x, cp.y);
    }
    ctx.lineTo(pts[pts.length - 1].x, pts[pts.length - 1].y);
    ctx.strokeStyle = lineColor;
    ctx.lineWidth   = 2;
    ctx.stroke();

    // ── Latest dot ────────────────────────────────────────────────────────
    const last = pts[pts.length - 1];
    ctx.beginPath();
    ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = lineColor;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(last.x, last.y, 7, 0, Math.PI * 2);
    ctx.strokeStyle = lineColor + "44";
    ctx.lineWidth = 2;
    ctx.stroke();

    // ── Y-axis labels ─────────────────────────────────────────────────────
    ctx.fillStyle  = "#334455";
    ctx.font       = "9px 'Courier New'";
    ctx.textAlign  = "left";
    const topLabel = cfg.invertY
      ? yMin.toFixed(0)      // top of canvas = low value for invertY
      : yMax.toFixed(0);
    const btmLabel = cfg.invertY
      ? yMax.toFixed(0)
      : yMin.toFixed(0);
    ctx.fillText(topLabel, 3, 10);
    ctx.fillText(btmLabel, 3, H - 3);

  }, [history, cfg, phase]);

  return (
    <canvas
      ref={canvasRef}
      width={500}
      height={90}
      style={{
        width: "100%",
        height: "90px",
        display: "block",
        borderRadius: 6,
        border: `1px solid ${cfg.gridColor}`,
        marginBottom: 10,
      }}
    />
  );
}

// ── Color helper ─────────────────────────────────────────────────────────────
function getColor(cfg, value) {
  if (cfg.higherBad) {
    if (value >= cfg.critAt) return cfg.critColor;
    if (value >= cfg.warnAt) return cfg.warnColor;
    return cfg.goodColor;
  } else {
    // lower is bad (bandwidth)
    if (value <= cfg.critAt) return cfg.critColor;
    if (value <= cfg.warnAt) return cfg.warnColor;
    return cfg.goodColor;
  }
}

// ── Per-metric card ───────────────────────────────────────────────────────────
function MetricCard({ cfg, history, phase }) {
  if (!history.length) return null;

  const vals      = history.map(h => h[cfg.key] ?? 0);
  const current   = vals[vals.length - 1];
  const minVal    = Math.min(...vals);
  const maxVal    = Math.max(...vals);
  const avgVal    = vals.reduce((a, b) => a + b, 0) / vals.length;
  const color     = getColor(cfg, current);

  // Spike detection
  const isSpike = cfg.higherBad
    ? current >= cfg.critAt
    : current <= cfg.critAt;
  const isWarn  = cfg.higherBad
    ? current >= cfg.warnAt && current < cfg.critAt
    : current <= cfg.warnAt && current > cfg.critAt;

  const statusLabel = isSpike ? "⚠ CRITICAL" : isWarn ? "! WARNING" : "● NOMINAL";
  const statusColor = isSpike ? cfg.critColor : isWarn ? cfg.warnColor : cfg.goodColor;

  return (
    <div style={{
      background: cfg.bgColor,
      border: `1px solid ${isSpike ? cfg.critColor + "88" : cfg.gridColor}`,
      borderRadius: 8,
      padding: "12px 14px",
      marginBottom: 12,
      boxShadow: isSpike ? `0 0 12px ${cfg.critColor}33` : "none",
      transition: "box-shadow 0.3s ease",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: "9px", color: "#334455", letterSpacing: "2.5px", marginBottom: 4 }}>
            {cfg.label}
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
            <span style={{
              fontSize: "26px", fontWeight: 900, color,
              fontFamily: "'Courier New', monospace",
              textShadow: `0 0 12px ${color}66`,
              lineHeight: 1,
            }}>
              {current.toFixed(1)}
            </span>
            <span style={{ fontSize: "11px", color: "#4a6a8a" }}>{cfg.unit}</span>
          </div>
          <div style={{ fontSize: "9px", color: "#2a4a6a", marginTop: 3 }}>{cfg.description}</div>
        </div>

        {/* Status badge */}
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4
        }}>
          <div style={{
            background: statusColor + "22",
            border: `1px solid ${statusColor}55`,
            borderRadius: 4,
            padding: "3px 8px",
            animation: isSpike ? "blink 0.6s infinite" : "none",
          }}>
            <span style={{ fontSize: "9px", color: statusColor, fontWeight: 800, letterSpacing: "1px" }}>
              {statusLabel}
            </span>
          </div>

          {/* Change indicator */}
          {vals.length >= 3 && (() => {
            const prev = vals[vals.length - 3];
            const diff = current - prev;
            const pct  = prev ? Math.abs(diff / prev * 100) : 0;
            if (pct < 2) return null;
            const up = diff > 0;
            const arrowColor = (cfg.higherBad ? up : !up) ? cfg.critColor : cfg.goodColor;
            return (
              <div style={{ fontSize: "10px", color: arrowColor, fontWeight: 700 }}>
                {up ? "▲" : "▼"} {pct.toFixed(0)}%
              </div>
            );
          })()}
        </div>
      </div>

      {/* Graph */}
      <Sparkline history={history} cfg={cfg} phase={phase} />

      {/* Stats row */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(5, 1fr)",
        gap: 6,
        fontSize: "9px",
        borderTop: `1px solid ${cfg.gridColor}`,
        paddingTop: 8,
      }}>
        {[
          ["MIN",  minVal.toFixed(1), null],
          ["AVG",  avgVal.toFixed(1), null],
          ["MAX",  maxVal.toFixed(1), null],
          ["WARN", cfg.warnAt,        cfg.warnColor],
          ["CRIT", cfg.critAt,        cfg.critColor],
        ].map(([lbl, val, col]) => (
          <div key={lbl} style={{ textAlign: "center" }}>
            <div style={{ color: "#334455", letterSpacing: "1px", marginBottom: 2 }}>{lbl}</div>
            <div style={{
              color: col ?? "#8899aa",
              fontWeight: 700,
              fontFamily: "'Courier New', monospace",
            }}>
              {val}<span style={{ fontSize: "8px", opacity: 0.7 }}>{cfg.unit}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Health banner ─────────────────────────────────────────────────────────────
function HealthBanner({ snapshot, phase }) {
  const phaseColor =
    phase === "attack"    ? "#ff4444" :
    phase === "consensus" ? "#cc88ff" : "#00ff88";

  const phaseLabel =
    phase === "attack"    ? "⚠ ATTACK ACTIVE — METRICS SPIKING" :
    phase === "consensus" ? "◈ PBFT CONSENSUS — LINKS SATURATED" :
    "● NOMINAL — ALL LINKS HEALTHY";

  let health = 100;
  if (snapshot) {
    METRICS_CONFIG.forEach(cfg => {
      const v = snapshot[cfg.key] ?? 0;
      const penalty = cfg.higherBad
        ? Math.min(v / (cfg.critAt * 2), 1)
        : 1 - Math.min(v / cfg.baselineMax, 1);
      health -= penalty * (100 / METRICS_CONFIG.length);
    });
    health = Math.max(0, Math.round(health));
  }

  const healthColor = health > 70 ? "#00ff88" : health > 40 ? "#ffcc00" : "#ff3333";

  return (
    <div style={{
      background: "#060f1e",
      border: `1px solid ${phaseColor}33`,
      borderRadius: 6,
      padding: "10px 14px",
      marginBottom: 12,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            background: phaseColor,
            boxShadow: `0 0 6px ${phaseColor}`,
            animation: phase !== "idle" ? "blink 0.8s infinite" : "none",
          }} />
          <span style={{ fontSize: "10px", color: phaseColor, fontWeight: 800, letterSpacing: "1.5px" }}>
            {phaseLabel}
          </span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: "8px", color: "#334455", letterSpacing: "1px" }}>NET HEALTH</div>
          <div style={{
            fontSize: "18px", fontWeight: 900, color: healthColor,
            textShadow: `0 0 10px ${healthColor}`,
            fontFamily: "'Courier New', monospace",
            lineHeight: 1,
          }}>
            {health}<span style={{ fontSize: "10px" }}>%</span>
          </div>
        </div>
      </div>
      <div style={{ height: 4, background: "#0d2137", borderRadius: 2, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: `${health}%`,
          background: `linear-gradient(90deg, ${healthColor}88, ${healthColor})`,
          borderRadius: 2,
          boxShadow: `0 0 8px ${healthColor}`,
          transition: "width 0.4s ease, background 0.4s ease",
        }} />
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MetricsGraphs({ edgeMetrics, phase }) {
  const [history,   setHistory]   = useState([]);
  const [activeTab, setActiveTab] = useState("all");

  useEffect(() => {
    if (!edgeMetrics || Object.keys(edgeMetrics).length === 0) return;

    // Use weighted average so attack spikes aren't diluted
    const snap = {};
    for (const cfg of METRICS_CONFIG) {
      snap[cfg.key] = weightedAvg(edgeMetrics, cfg.key, cfg.higherBad);
    }

    setHistory(prev => {
      const next = [...prev, snap];
      // During idle, keep a shorter window so baseline is clear
      return next.slice(-MAX_POINTS);
    });
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
    activeTab === "all"
      ? METRICS_CONFIG
      : METRICS_CONFIG.filter(m => m.key === activeTab);

  const latestSnap = history[history.length - 1] ?? null;

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      background: "#040d18",
      fontFamily: "'Courier New', monospace",
      overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "10px 14px 6px",
        borderBottom: "1px solid #0d2137",
        flexShrink: 0,
      }}>
        <div style={{ fontSize: "9px", color: "#4a9aba", letterSpacing: "3px", marginBottom: 8 }}>
          ◈ LIVE NETWORK METRICS
        </div>
        <HealthBanner snapshot={latestSnap} phase={phase} />

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {TABS.map(({ key, label }) => (
            <button key={key} onClick={() => setActiveTab(key)} style={{
              flex: 1,
              padding: "5px 4px",
              background: activeTab === key ? "#0d2a40" : "#060f1e",
              border: `1px solid ${activeTab === key ? "#44ccff66" : "#0d2137"}`,
              borderRadius: 4,
              color: activeTab === key ? "#44ccff" : "#2a5a7a",
              fontSize: "9px",
              fontWeight: 700,
              letterSpacing: "1px",
              cursor: "pointer",
              fontFamily: "'Courier New', monospace",
              transition: "all 0.15s",
            }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Cards */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px" }}>
        {history.length < 2 ? (
          <div style={{ textAlign: "center", color: "#1a4a6a", fontSize: "11px", marginTop: 30 }}>
            Waiting for metrics…
          </div>
        ) : (
          visibleMetrics.map(cfg => (
            <MetricCard
              key={cfg.key}
              cfg={cfg}
              history={history}
              phase={phase}
            />
          ))
        )}
      </div>

      <style>{`
        @keyframes blink {
          0%,100% { opacity: 1; }
          50%      { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
}