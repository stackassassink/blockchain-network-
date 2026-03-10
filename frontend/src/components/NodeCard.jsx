const STATUS_LABEL = {
  healthy:     { label: "HEALTHY",     color: "#00e676" },
  compromised: { label: "COMPROMISED", color: "#ff3e3e" },
  quarantined: { label: "QUARANTINED", color: "#ff9800" },
  healing:     { label: "HEALING",     color: "#00bcd4" },
  suspect:     { label: "SUSPECT",     color: "#ffd600" },
  validator:   { label: "VALIDATOR",   color: "#b388ff" },
};

const Row = ({ label, value, color }) => (
  <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #0d2137" }}>
    <span style={{ fontSize: "10px", color: "#1e5080", letterSpacing: "1px" }}>{label}</span>
    <span className="font-mono-tech" style={{ fontSize: "11px", color: color ?? "#c8e6ff" }}>{value}</span>
  </div>
);

export default function NodeCard({ node }) {
  const statusInfo = STATUS_LABEL[node?.status] ?? { label: "UNKNOWN", color: "#546e7a" };
  const reputation = node?.reputation ?? 0;

  // Fix: map backend field names to display values
  const blockCount  = node?.block_count ?? 0;
  const connections = node?.connected_peers?.length ?? 0;
  const txRate      = node?.tx_rate ?? 0;
  const latency     = node?.latency ?? 0;
  const attackType  = node?.attack_type ?? null;

  return (
    <div
      style={{
        width: "200px",
        minWidth: "200px",
        background: "linear-gradient(180deg, #060f1e 0%, #040d18 100%)",
        borderLeft: "1px solid #0d2137",
        padding: "12px",
        overflowY: "auto",
      }}
    >
      <div
        className="font-mono-tech"
        style={{ fontSize: "10px", color: "#4fc3f7", letterSpacing: "2px", marginBottom: "12px", borderBottom: "1px solid #0d2137", paddingBottom: "8px" }}
      >
        ◈ NODE DETAILS
      </div>

      {!node ? (
        <div style={{ color: "#1e5080", fontSize: "11px", fontFamily: "'Share Tech Mono', monospace", textAlign: "center", paddingTop: "32px" }}>
          Click a node<br />to inspect
        </div>
      ) : (
        <>
          {/* Status badge */}
          <div
            style={{
              background: `${statusInfo.color}18`,
              border: `1px solid ${statusInfo.color}44`,
              borderRadius: "4px",
              padding: "6px 10px",
              marginBottom: "12px",
              textAlign: "center",
            }}
          >
            <span className="font-mono-tech" style={{ color: statusInfo.color, fontSize: "12px", letterSpacing: "2px" }}>
              {statusInfo.label}
            </span>
          </div>

          <Row label="NODE ID"     value={node.id ?? "—"} />
          <Row label="BLOCK #"     value={blockCount}      color="#4fc3f7" />
          <Row label="TX RATE"     value={`${txRate}/s`}   color="#b388ff" />
          <Row label="CONNECTIONS" value={connections}     />
          <Row label="LATENCY"     value={`${latency}ms`}  color={latency > 200 ? "#ff9800" : "#00e676"} />

          {/* Reputation bar */}
          <div style={{ marginTop: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
              <span style={{ fontSize: "10px", color: "#1e5080", letterSpacing: "1px" }}>REPUTATION</span>
              <span className="font-mono-tech" style={{ fontSize: "10px", color: reputation > 60 ? "#00e676" : "#ff3e3e" }}>
                {Math.round(reputation)}%
              </span>
            </div>
            <div style={{ height: "4px", background: "#0d2137", borderRadius: "2px", overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  width: `${reputation}%`,
                  background: reputation > 60
                    ? "linear-gradient(90deg, #00e676, #00bcd4)"
                    : "linear-gradient(90deg, #ff3e3e, #ff9800)",
                  borderRadius: "2px",
                  transition: "width 0.4s ease",
                }}
              />
            </div>
          </div>

          {/* Attack type badge */}
          {attackType && (
            <div style={{ marginTop: "12px" }}>
              <div style={{ fontSize: "10px", color: "#1e5080", letterSpacing: "1px", marginBottom: "4px" }}>ATTACK TYPE</div>
              <div
                className="font-mono-tech"
                style={{
                  fontSize: "11px", color: "#ff3e3e",
                  background: "#ff3e3e18", border: "1px solid #ff3e3e44",
                  borderRadius: "4px", padding: "4px 8px",
                }}
              >
                ⚠ {attackType.toUpperCase()}
              </div>
            </div>
          )}

          {/* Peers list */}
          {node.connected_peers?.length > 0 && (
            <div style={{ marginTop: "12px" }}>
              <div style={{ fontSize: "10px", color: "#1e5080", letterSpacing: "1px", marginBottom: "4px" }}>PEERS</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {node.connected_peers.map((p, i) => (
                  <span
                    key={i}
                    className="font-mono-tech"
                    style={{
                      fontSize: "10px", color: "#4fc3f7",
                      background: "#4fc3f718", border: "1px solid #4fc3f733",
                      borderRadius: "3px", padding: "2px 6px",
                    }}
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}