export default function ConsensusBar({ votes, nodes }) {
  const total  = nodes.length || 1;
  const entries = Object.values(votes);
  const latest  = entries[entries.length - 1];
  const count   = latest?.count ?? 0;
  const needed  = latest?.needed ?? Math.floor(total * 0.67) + 1;
  const pct     = Math.min(100, Math.round((count / needed) * 100));

  return (
    <div style={{ background: "#060f1eee", border: "1px solid #b388ff44", borderRadius: "8px", padding: "16px 20px", backdropFilter: "blur(8px)", boxShadow: "0 0 24px #b388ff22" }}>
      <div style={{ fontSize: "10px", color: "#b388ff", letterSpacing: "2px", marginBottom: "10px", fontFamily: "monospace" }}>
        PBFT CONSENSUS ROUND
      </div>
      <div style={{ height: "8px", background: "#0d2137", borderRadius: "4px", overflow: "hidden", marginBottom: "10px" }}>
        <div style={{ height: "100%", width: pct + "%", background: pct >= 100 ? "linear-gradient(90deg,#00e676,#00bcd4)" : "linear-gradient(90deg,#b388ff,#7c4dff)", borderRadius: "4px", transition: "width 0.4s ease" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontFamily: "monospace" }}>
        <span style={{ color: "#00e676" }}>VOTES: {count}</span>
        <span style={{ color: "#b388ff" }}>{pct}%</span>
        <span style={{ color: "#546e7a" }}>NEEDED: {needed}</span>
        <span style={{ color: pct >= 100 ? "#00e676" : "#ffd600" }}>{pct >= 100 ? "QUORUM REACHED" : "VOTING..."}</span>
      </div>
    </div>
  );
}