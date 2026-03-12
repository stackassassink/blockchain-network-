// ConsensusBar.jsx — fixed to read votes.round from backend
// Backend emits: { "round": { count, needed, total } }
// Shows per-node voter dots + animated progress bar

export default function ConsensusBar({ votes, nodes }) {
  // Backend sends { round: { count, needed, total } }
  const round       = votes?.round ?? {};
  const count       = round.count  ?? 0;
  const needed      = round.needed ?? Math.floor((nodes.length || 7) * 0.67) + 1;
  const total       = round.total  ?? nodes.length ?? 7;
  const pct         = needed > 0 ? Math.min(100, Math.round((count / needed) * 100)) : 0;
  const quorumMet   = count >= needed;

  // Build voter dot array — filled up to count, empty after
  const dots = Array.from({ length: total }, (_, i) => i < count);

  return (
    <div style={{
      background: "#060f1eee",
      border: `1px solid ${quorumMet ? "#00e67666" : "#b388ff44"}`,
      borderRadius: "8px",
      padding: "14px 20px",
      backdropFilter: "blur(8px)",
      boxShadow: `0 0 24px ${quorumMet ? "#00e67622" : "#b388ff22"}`,
      transition: "border-color 0.3s, box-shadow 0.3s",
    }}>

      {/* Title */}
      <div style={{
        fontSize: "10px", color: "#b388ff",
        letterSpacing: "2px", marginBottom: "10px",
        fontFamily: "monospace", fontWeight: 700,
      }}>
        PBFT CONSENSUS ROUND
      </div>

      {/* Progress bar */}
      <div style={{
        height: "8px", background: "#0d2137",
        borderRadius: "4px", overflow: "hidden", marginBottom: "10px",
      }}>
        <div style={{
          height: "100%",
          width: pct + "%",
          background: quorumMet
            ? "linear-gradient(90deg,#00e676,#00bcd4)"
            : "linear-gradient(90deg,#b388ff,#7c4dff)",
          borderRadius: "4px",
          transition: "width 0.35s ease",
          boxShadow: quorumMet ? "0 0 8px #00e67688" : "0 0 8px #b388ff44",
        }} />
      </div>

      {/* Voter dots — one per eligible node */}
      <div style={{
        display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap",
      }}>
        {dots.map((voted, i) => (
          <div key={i} style={{
            width: 10, height: 10, borderRadius: "50%",
            background: voted
              ? (quorumMet ? "#00e676" : "#b388ff")
              : "#0d2137",
            border: `1px solid ${voted ? (quorumMet ? "#00e676" : "#7c4dff") : "#1a3a5a"}`,
            boxShadow: voted ? `0 0 6px ${quorumMet ? "#00e67688" : "#b388ff88"}` : "none",
            transition: "all 0.25s ease",
          }} />
        ))}
      </div>

      {/* Stats row */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        fontSize: "11px", fontFamily: "monospace",
      }}>
        <span style={{ color: "#00e676" }}>VOTES: {count}/{total}</span>
        <span style={{ color: "#b388ff" }}>{pct}%</span>
        <span style={{ color: "#546e7a" }}>NEEDED: {needed}</span>
        <span style={{ color: quorumMet ? "#00e676" : "#ffd600" }}>
          {quorumMet ? "✅ QUORUM REACHED" : "⏳ VOTING..."}
        </span>
      </div>

    </div>
  );
}