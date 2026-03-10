const ATTACKS = [
  { label: "51% Attack",     type: "sybil",   color: "#ff3e3e", icon: "⚡" },
  { label: "Sybil Attack",   type: "sybil",   color: "#ff6b35", icon: "👥" },
  { label: "Eclipse Node",   type: "eclipse", color: "#ff9800", icon: "🌑" },
  { label: "Double Spend",   type: "sybil",   color: "#ffcc00", icon: "💸" },
  { label: "DDoS Node",      type: "dos",     color: "#e040fb", icon: "💥" },
  { label: "Routing Attack", type: "eclipse", color: "#ff5252", icon: "🔀" },
];

export default function AttackPanel({ socket, nodes, phase }) {
  const handleAttack = async (type) => {
    // Pick a random healthy node as target
    const healthy = nodes.filter(n => n.status === "healthy");
    if (!healthy.length) {
      alert("No healthy nodes to attack!");
      return;
    }
    const target = healthy[Math.floor(Math.random() * healthy.length)];

    try {
      const res = await fetch("http://127.0.0.1:5000/api/attack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, target: target.id }),
      });
      const data = await res.json();
      if (data.error) console.error("Attack error:", data.error);
    } catch (err) {
      console.error("Attack failed:", err);
    }
  };

  const handleHeal = async () => {
    try {
      await fetch("http://127.0.0.1:5000/api/heal", { method: "POST" });
    } catch (err) {
      console.error("Heal failed:", err);
    }
  };

  const handleReset = async () => {
    try {
      await fetch("http://127.0.0.1:5000/api/reset", { method: "POST" });
    } catch (err) {
      console.error("Reset failed:", err);
    }
  };

  return (
    <div
      className="flex flex-col gap-2 p-3 overflow-y-auto"
      style={{
        width: "180px",
        minWidth: "180px",
        background: "linear-gradient(180deg, #060f1e 0%, #040d18 100%)",
        borderRight: "1px solid #0d2137",
      }}
    >
      <div
        className="font-mono-tech text-xs mb-2 tracking-widest"
        style={{ color: "#4fc3f7", borderBottom: "1px solid #0d2137", paddingBottom: "8px" }}
      >
        ⚔ ATTACK CONSOLE
      </div>

      {ATTACKS.map(({ label, type, color, icon }) => (
        <button
          key={label}
          onClick={() => handleAttack(type)}
          disabled={phase === "consensus"}
          style={{
            background: "transparent",
            border: `1px solid ${color}33`,
            borderLeft: `3px solid ${color}`,
            color: color,
            padding: "8px 10px",
            borderRadius: "4px",
            cursor: phase === "consensus" ? "not-allowed" : "pointer",
            fontSize: "11px",
            fontFamily: "'Share Tech Mono', monospace",
            textAlign: "left",
            transition: "all 0.15s",
            opacity: phase === "consensus" ? 0.4 : 1,
          }}
          onMouseEnter={e => {
            if (phase !== "consensus") {
              e.currentTarget.style.background = `${color}18`;
              e.currentTarget.style.boxShadow  = `0 0 8px ${color}44`;
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.boxShadow  = "none";
          }}
        >
          <span style={{ marginRight: "6px" }}>{icon}</span>{label}
        </button>
      ))}

      <div style={{ borderTop: "1px solid #0d2137", marginTop: "8px", paddingTop: "8px" }} />

      <button
        onClick={handleHeal}
        style={{
          background: "transparent",
          border: "1px solid #00e67633",
          borderLeft: "3px solid #00e676",
          color: "#00e676",
          padding: "8px 10px",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "11px",
          fontFamily: "'Share Tech Mono', monospace",
          textAlign: "left",
          transition: "all 0.15s",
        }}
        onMouseEnter={e => {
          e.currentTarget.style.background = "#00e67618";
          e.currentTarget.style.boxShadow  = "0 0 8px #00e67644";
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = "transparent";
          e.currentTarget.style.boxShadow  = "none";
        }}
      >
        <span style={{ marginRight: "6px" }}>💊</span>Heal All Nodes
      </button>

      <button
        onClick={handleReset}
        style={{
          background: "transparent",
          border: "1px solid #4fc3f733",
          borderLeft: "3px solid #4fc3f7",
          color: "#4fc3f7",
          padding: "8px 10px",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "11px",
          fontFamily: "'Share Tech Mono', monospace",
          textAlign: "left",
          transition: "all 0.15s",
        }}
        onMouseEnter={e => {
          e.currentTarget.style.background = "#4fc3f718";
          e.currentTarget.style.boxShadow  = "0 0 8px #4fc3f744";
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = "transparent";
          e.currentTarget.style.boxShadow  = "none";
        }}
      >
        <span style={{ marginRight: "6px" }}>🔄</span>Reset Network
      </button>

      <div
        className="font-mono-tech mt-auto text-center"
        style={{ color: "#1e5080", fontSize: "10px", paddingTop: "12px" }}
      >
        {nodes.filter(n => n.status === "healthy").length} nodes available
      </div>
    </div>
  );
}