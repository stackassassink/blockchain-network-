const LOG_COLORS = {
  error:   "#ff3333",
  warning: "#ffee00",
  success: "#00ff88",
  block:   "#00ddff",
  info:    "#aaddff",
};

export default function LogFeed({ logs = [] }) {
  return (
    <div style={{
      height:"160px", background:"#010b14",
      borderTop:"1px solid #0d2137",
      overflow:"hidden", flexShrink:0,
      fontFamily:"'Courier New',monospace",
      display:"flex", flexDirection:"column",
    }}>

      {/* Header — fixed at top */}
      <div style={{
        padding:"5px 14px",
        borderBottom:"1px solid #0d2137",
        display:"flex", justifyContent:"space-between",
        alignItems:"center", flexShrink:0,
        background:"#010b14",
      }}>
        <span style={{
          fontSize:"10px", color:"#2a6a8a",
          letterSpacing:"3px", fontWeight:700,
        }}>
          LIVE EVENT LOG
        </span>
        <span style={{ fontSize:"10px", color:"#1a4a6a" }}>
          {logs.length} events · latest on top
        </span>
      </div>

      {/* Log entries — newest first, scrollable */}
      <div style={{
        flex:1,
        overflowY:"auto",
        display:"flex",
        flexDirection:"column",
        padding:"2px 0",
      }}>
        {logs.map((log, i) => {
          const color = LOG_COLORS[log.type] ?? "#aaddff";
          return (
            <div key={i} style={{
              padding:"2px 14px",
              display:"flex", gap:10,
              alignItems:"baseline",
              opacity: Math.max(0.35, 1 - i * 0.018),
              fontSize:"11px",
              borderBottom:"1px solid #0a1520",
            }}>
              <span style={{
                color:"#1a4a6a", flexShrink:0,
                fontSize:"10px", minWidth:"70px",
              }}>
                {log.timestamp
                  ? new Date(log.timestamp).toLocaleTimeString()
                  : ""}
              </span>
              <span style={{
                color, fontWeight:700, flexShrink:0,
                fontSize:"10px", letterSpacing:"1px",
                minWidth:"70px",
              }}>
                [{log.type?.toUpperCase() ?? "INFO"}]
              </span>
              <span style={{ color:"#8ab8cc" }}>
                {log.message}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}