// StatsBar.jsx — v3 fixes:
//   1. faultStr NOW RENDERED (was computed but never shown)
//   2. f and Q read from backend stats — dynamic, not hardcoded
//   3. VIABILITY badge added, colour-coded per tier
//   4. Phase colours extended for critical/frozen/dead/paused

const PHASE_COLOR = {
  idle:      "#4fc3f7",
  attack:    "#ff3e3e",
  consensus: "#b388ff",
  healing:   "#00e676",
  critical:  "#ff3e3e",
  frozen:    "#ff9800",
  dead:      "#546e7a",
  paused:    "#ffaa00",
  default:   "#546e7a",
};

const VIABILITY_COLOR = {
  operational: "#00e676",
  critical:    "#ff3e3e",
  frozen:      "#ff9800",
  dead:        "#546e7a",
};

export default function StatsBar({ nodes, phase, stats = {} }) {
  const healthy     = nodes.filter(n => n.status === "healthy").length;
  const compromised = nodes.filter(n => n.status === "compromised").length;
  const quarantined = nodes.filter(n => n.status === "quarantined").length;
  const total       = nodes.length;

  // Read from backend stats — computed correctly after every quarantine (v5)
  // Falls back to safe defaults if backend hasn't sent v5 stats yet
  const quorum    = stats.quorum === 0 ? "N/A" : (stats.quorum ?? 5)
  const hCount    = stats.healthy_count ?? healthy;
  const f         = Math.floor((hCount - 1) / 3);
  const viability = stats.viability     ?? "operational";

  // RENDERED below brand name — updates live
  const faultStr  = `NODES: ${total}  |  f=${f}  |  Q:${quorum}`;

  const blockHeight = stats.block_count ?? 0;
  const txRate      = (stats.tx_rate    ?? 0).toFixed(1);

  const phaseColor     = PHASE_COLOR[phase]         ?? PHASE_COLOR.default;
  const viabilityColor = VIABILITY_COLOR[viability] ?? "#4fc3f7";

  const Stat = ({ label, value, color }) => (
    <div style={{
      textAlign: "center",
      padding: "0 14px",
      borderRight: "1px solid #0d2137",
      flexShrink: 0,
    }}>
      <div
        className="font-mono-tech"
        style={{ fontSize: "18px", color: color ?? "#c8e6ff", fontWeight: 600 }}
      >
        {value}
      </div>
      <div style={{ fontSize: "9px", color: "#1e5080", letterSpacing: "1.5px", marginTop: "2px" }}>
        {label}
      </div>
    </div>
  );

  return (
    <div style={{
      height: "56px",
      background: "linear-gradient(90deg, #060f1e 0%, #040d18 50%, #060f1e 100%)",
      borderBottom: "1px solid #0d2137",
      display: "flex",
      alignItems: "center",
      padding: "0 16px",
      gap: "0",
      flexShrink: 0,
    }}>

      {/* Brand + live PBFT params */}
      <div style={{
        marginRight: "20px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 2,
        flexShrink: 0,
      }}>
        <span
          className="font-mono-tech"
          style={{ fontSize: "14px", color: "#4fc3f7", letterSpacing: "3px", fontWeight: 700 }}
        >
          BLOCKCHAIN<span style={{ color: "#ff3e3e" }}>SEC</span>
        </span>
        {/* faultStr rendered here — updates every stats_update event */}
        <span
          className="font-mono-tech"
          style={{ fontSize: "9px", color: "#2a6a8a", letterSpacing: "1.5px" }}
        >
          {faultStr}
        </span>
      </div>

      {/* Stats */}
      <Stat label="TOTAL NODES"  value={total}       />
      <Stat label="HEALTHY"      value={healthy}     color="#00e676" />
      <Stat label="COMPROMISED"  value={compromised} color="#ff3e3e" />
      <Stat label="QUARANTINED"  value={quarantined} color="#ff9800" />
      <Stat label="BLOCK HEIGHT" value={blockHeight} color="#4fc3f7" />
      <Stat label="TX/s"         value={txRate}      color="#b388ff" />

      {/* Viability tier badge */}
      <div style={{
        padding: "0 14px",
        borderRight: "1px solid #0d2137",
        textAlign: "center",
        flexShrink: 0,
      }}>
        <div
          className="font-mono-tech"
          style={{
            fontSize: "11px",
            color: viabilityColor,
            fontWeight: 700,
            textShadow: `0 0 8px ${viabilityColor}88`,
          }}
        >
          {viability.toUpperCase()}
        </div>
        <div style={{ fontSize: "9px", color: "#1e5080", letterSpacing: "1.5px", marginTop: "2px" }}>
          VIABILITY
        </div>
      </div>

      {/* Phase indicator */}
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
        <div style={{
          width: "8px", height: "8px", borderRadius: "50%",
          background: phaseColor,
          boxShadow: `0 0 8px ${phaseColor}`,
          animation: phase !== "idle" ? "glow-pulse 1s infinite" : "none",
        }} />
        <span
          className="font-mono-tech"
          style={{ fontSize: "11px", color: phaseColor, letterSpacing: "2px" }}
        >
          {phase.toUpperCase()}
        </span>
      </div>

    </div>
  );
}