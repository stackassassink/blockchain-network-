const PHASE_COLOR = {
  idle:      "#4fc3f7",
  attack:    "#ff3e3e",
  consensus: "#b388ff",
  healing:   "#00e676",
  default:   "#546e7a",
};

export default function StatsBar({ nodes, phase, stats = {} }) {
  const healthy     = nodes.filter(n => n.status === "healthy").length;
  const compromised = nodes.filter(n => n.status === "compromised").length;
  const quarantined = nodes.filter(n => n.status === "quarantined").length;
  const total       = nodes.length;

  // Use stats from backend, not from individual nodes
  const blockHeight = stats.block_count ?? 0;
  const txRate      = (stats.tx_rate ?? 0).toFixed(1);

  const phaseColor  = PHASE_COLOR[phase] ?? PHASE_COLOR.default;

  const Stat = ({ label, value, color }) => (
    <div style={{ textAlign: "center", padding: "0 16px", borderRight: "1px solid #0d2137" }}>
      <div className="font-mono-tech" style={{ fontSize: "18px", color: color ?? "#c8e6ff", fontWeight: 600 }}>
        {value}
      </div>
      <div style={{ fontSize: "9px", color: "#1e5080", letterSpacing: "1.5px", marginTop: "2px" }}>
        {label}
      </div>
    </div>
  );

  return (
    <div
      style={{
        height: "56px",
        background: "linear-gradient(90deg, #060f1e 0%, #040d18 50%, #060f1e 100%)",
        borderBottom: "1px solid #0d2137",
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        gap: "0",
        flexShrink: 0,
      }}
    >
      <div style={{ marginRight: "24px" }}>
        <span
          className="font-mono-tech"
          style={{ fontSize: "14px", color: "#4fc3f7", letterSpacing: "3px", fontWeight: 700 }}
        >
          BLOCKCHAIN<span style={{ color: "#ff3e3e" }}>SEC</span>
        </span>
      </div>

      <Stat label="TOTAL NODES"  value={total}       />
      <Stat label="HEALTHY"      value={healthy}     color="#00e676" />
      <Stat label="COMPROMISED"  value={compromised} color="#ff3e3e" />
      <Stat label="QUARANTINED"  value={quarantined} color="#ff9800" />
      <Stat label="BLOCK HEIGHT" value={blockHeight} color="#4fc3f7" />
      <Stat label="TX/s"         value={txRate}      color="#b388ff" />

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
        <div
          style={{
            width: "8px", height: "8px", borderRadius: "50%",
            background: phaseColor,
            boxShadow: `0 0 8px ${phaseColor}`,
            animation: phase !== "idle" ? "glow-pulse 1s infinite" : "none",
          }}
        />
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