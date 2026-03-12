import { useState, useEffect, useRef, useCallback } from "react";
import { io } from "socket.io-client";
import NetworkGraph  from "./components/NetworkGraph";
import LogFeed       from "./components/LogFeed";
import ConsensusBar  from "./components/ConsensusBar";
import MetricsPanel  from "./components/MetricsPanel";
import MetricsGraphs from "./components/MetricsGraphs";

const ATTACKS = [
  { label:"Byzantine Fault", desc:"Conflicting block broadcasts",
    type:"byzantine", icon:"⚔",  color:"#ff4444" },
  { label:"DDoS Flood",      desc:"Transaction spam overload",
    type:"dos",       icon:"💥", color:"#ff9800" },
];

const STATUS_COLOR = {
  healthy:"#00ff88", compromised:"#ff4444",
  quarantined:"#ffaa00", healing:"#00ddff", suspect:"#ffee00",
};

const PHASE_COLOR = {
  idle:      "#00ff88",
  attack:    "#ff4444",
  consensus: "#cc88ff",
  healing:   "#00ddff",
  paused:    "#ffaa00",
  critical:  "#ff3e3e",   // ← new
  frozen:    "#ff9800",   // ← new
  dead:      "#546e7a",   // ← new
};
const PHASE_LABEL = {
  idle:      "NETWORK STABLE",
  attack:    "UNDER ATTACK",
  consensus: "PBFT CONSENSUS",
  healing:   "HEALING",
  paused:    "⏸ NETWORK PAUSED",
  critical:  "⚠ CRITICAL — ZERO FAULT TOLERANCE",   // ← new
  frozen:    "🔒 FROZEN — READ ONLY",                // ← new
  dead:      "💀 DEAD — FULL PARTITION",             // ← new
};


function SLabel({ children }) {
  return (
    <div style={{
      fontSize:"11px", color:"#4a9aba", letterSpacing:"3px",
      marginBottom:"10px", marginTop:"8px", fontWeight:700,
    }}>
      {children}
    </div>
  );
}

export default function App() {
  const [nodes,          setNodes]          = useState([]);
  const [edges,          setEdges]          = useState([]);
  const [phase,          setPhase]          = useState("idle");
  const [logs,           setLogs]           = useState([]);
  const [consensusVotes, setConsensusVotes] = useState({});
  const [selectedNode,   setSelectedNode]   = useState(null);
  const [connected,      setConnected]      = useState(false);
  const [edgeMetrics,    setEdgeMetrics]    = useState({});
  const [showMetrics,    setShowMetrics]    = useState(true);
  const [showGraphs,     setShowGraphs]     = useState(false);
  const [stats, setStats] = useState({
    block_count:0, tx_rate:0, compromised_nodes:[],
  });

  // We accumulate single-edge events here so MetricsGraphs/Panel
  // always see a complete object (all edges present)
  const accumulatedMetrics = useRef({});

  const socketRef = useRef(null);

  useEffect(() => {
    const socket = io("http://localhost:5000", {
      transports:["websocket","polling"],
      reconnection:true, reconnectionDelay:1000,
      reconnectionAttempts:Infinity, timeout:10000,
    });
    socketRef.current = socket;

    socket.on("connect", () => {
      setConnected(true);
      socket.emit("request_state");
    });
    socket.on("disconnect",    () => setConnected(false));
    socket.on("connect_error", () => setConnected(false));

    socket.on("graph_update", ({ nodes:n, edges:e }) => {
      if (n) setNodes([...n]);
      if (e) setEdges([...e]);
    });
    socket.on("stats_update",    setStats);
    socket.on("phase_change",    ({ phase:p }) => {
      setPhase(p);
      if (p !== "consensus") setConsensusVotes({});
    });
    socket.on("log_event", e => setLogs(prev => [e,...prev].slice(0,300)));
    socket.on("consensus_votes", v => setConsensusVotes(prev => ({...prev,...v})));

    // ── NEW backend: all 10 edges in one shot ─────────────────────────────
    socket.on("all_edge_metrics", (metricsMap) => {
      accumulatedMetrics.current = metricsMap;
      setEdgeMetrics({ ...metricsMap });
    });

    // ── OLD backend: one edge at a time — accumulate into full object ─────
    // This handler fires on every comms tick with one edge's data.
    // We merge it into accumulatedMetrics and push the whole object to state
    // so MetricsGraphs gets a fresh reference (triggering its useEffect)
    // with ALL known edges, not just the one that just arrived.
    socket.on("edge_metrics_update", (m) => {
      accumulatedMetrics.current = {
        ...accumulatedMetrics.current,
        [m.edge_key]: m,
      };
      // Only push to state once we have at least 3 edges populated
      // (avoids premature averages with 1/10 edges)
      if (Object.keys(accumulatedMetrics.current).length >= 3) {
        setEdgeMetrics({ ...accumulatedMetrics.current });
      }
    });

    return () => { socket.removeAllListeners(); socket.disconnect(); };
  }, []);

  const doAttack = useCallback((type) => {
    const healthy = nodes.filter(n => n.status === "healthy");
    if (!healthy.length) return;
    const target = healthy[Math.floor(Math.random() * healthy.length)];
    fetch("http://localhost:5000/api/attack", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ type, target:target.id }),
    }).catch(console.error);
  }, [nodes]);

  const doReset = useCallback(() => {
    setIsPaused(false);
    setConsensusVotes({});
    setLogs([]);                        
    accumulatedMetrics.current = {};
    setEdgeMetrics({});

    fetch("http://localhost:5000/api/reset", { method: "POST" })
      .then(() => {
        return new Promise(r => setTimeout(r, 400));
      })
      .then(() =>
        fetch("http://localhost:5000/api/metrics")
          .then(r => r.json())
          .then(data => {
            if (data && typeof data === "object" && !data.error) {
              accumulatedMetrics.current = data;
              setEdgeMetrics({ ...data });
            }
          })
      )
      .catch(console.error);
  }, []);
  
  const [isPaused, setIsPaused] = useState(false);

  const doPause = useCallback(() => {
    const endpoint = isPaused ? "/api/resume" : "/api/pause";
    fetch(`http://localhost:5000${endpoint}`, { method: "POST" })
      .then(() => {
        // After resume, re-fetch metrics so panel doesn't stay frozen
        if (isPaused) {
          return new Promise(r => setTimeout(r, 400))
            .then(() =>
              fetch("http://localhost:5000/api/metrics")
                .then(r => r.json())
                .then(data => {
                  if (data && typeof data === "object" && !data.error) {
                    accumulatedMetrics.current = data;
                    setEdgeMetrics({ ...data });
                  }
                })
            );
        }
      })
      .catch(console.error);
    setIsPaused(v => !v);
  }, [isPaused]);

  // Seed initial metrics via REST on connect so panel isn't blank at startup
  useEffect(() => {
    if (!connected) return;
    fetch("http://localhost:5000/api/metrics")
      .then(r => r.json())
      .then(data => {
        if (data && typeof data === "object" && !data.error) {
          accumulatedMetrics.current = data;
          setEdgeMetrics({ ...data });
        }
      })
      .catch(() => {});
  }, [connected]);

  const healthy        = nodes.filter(n => n.status === "healthy").length;
  const compromised    = nodes.filter(n =>
    ["compromised","suspect","quarantined"].includes(n.status)).length;
  const currentPrimary = nodes.find(n => n.is_primary);
  const phaseColor     = PHASE_COLOR[phase] ?? "#44ccff";

  return (
    <div style={{
      display:"flex", flexDirection:"column",
      height:"100vh", width:"100vw",
      background:"#050d1a", color:"#d0eeff",
      fontFamily:"'Courier New',monospace", overflow:"hidden",
    }}>

      {/* HEADER */}
      <div style={{
        padding:"10px 20px",
        borderBottom:"1px solid #0d2137",
        background:"linear-gradient(90deg,#060f1e,#040d18,#060f1e)",
        display:"flex", alignItems:"center",
        justifyContent:"space-between", flexShrink:0,
      }}>
        <div>
          <div style={{ fontSize:"19px", fontWeight:800,
                        letterSpacing:"2px", color:"#fff" }}>
            <span style={{ color:"#00ff88" }}>⬡⬡ </span>
            SELF-HEALING BLOCKCHAIN NETWORK
          </div>
          <div style={{ fontSize:"9px", color:"#2a7a9a",
                        letterSpacing:"3px", marginTop:"2px" }}>
            DECENTRALISED · ROTATING PRIMARY · PBFT · NO PERMANENT LEADER
          </div>
        </div>

        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <button onClick={() => setShowMetrics(v => !v)} style={{
            fontSize:"11px", padding:"6px 12px", borderRadius:"6px",
            background: showMetrics ? "#44ccff18" : "#060f1e",
            border:`1px solid ${showMetrics ? "#44ccff66" : "#0d2137"}`,
            color: showMetrics ? "#44ccff" : "#2a5a7a",
            fontWeight:700, letterSpacing:"1px", cursor:"pointer",
            transition:"all 0.2s", fontFamily:"'Courier New',monospace",
          }}>
            📊 {showMetrics ? "HIDE" : "SHOW"} METRICS
          </button>

          <button onClick={() => setShowGraphs(v => !v)} style={{
            fontSize:"11px", padding:"6px 12px", borderRadius:"6px",
            background: showGraphs ? "#00ff8818" : "#060f1e",
            border:`1px solid ${showGraphs ? "#00ff8866" : "#0d2137"}`,
            color: showGraphs ? "#00ff88" : "#2a5a7a",
            fontWeight:700, letterSpacing:"1px", cursor:"pointer",
            transition:"all 0.2s", fontFamily:"'Courier New',monospace",
          }}>
            📈 {showGraphs ? "HIDE" : "SHOW"} GRAPHS
          </button>

          <div style={{
            fontSize:"11px", padding:"6px 12px", borderRadius:"6px",
            background: connected ? "#00ff8811" : "#ff444411",
            border:`1px solid ${connected ? "#00ff8844" : "#ff444444"}`,
            color: connected ? "#00ff88" : "#ff4444",
            fontWeight:700, letterSpacing:"1px",
          }}>
            {connected ? "● LIVE" : "○ RECONNECTING..."}
          </div>

          {currentPrimary && (
            <div style={{
              border:"1px solid #bb88ff66", borderRadius:"6px",
              padding:"6px 12px", background:"#bb88ff11",
              fontSize:"11px", color:"#bb88ff", fontWeight:700,
            }}>
              🔄 PRIMARY: {currentPrimary.id}
            </div>
          )}

          <div style={{
            border:`2px solid ${phaseColor}`, borderRadius:"8px",
            padding:"8px 16px", background:`${phaseColor}18`,
            display:"flex", alignItems:"center", gap:8,
            boxShadow:`0 0 16px ${phaseColor}33`,
          }}>
            <div style={{
              width:9, height:9, borderRadius:"50%",
              background:phaseColor, boxShadow:`0 0 8px ${phaseColor}`,
              animation: phase !== "idle" ? "blink 0.8s infinite" : "none",
            }} />
            <span style={{ color:phaseColor, fontSize:"12px",
                           letterSpacing:"2px", fontWeight:800 }}>
              {PHASE_LABEL[phase] ?? phase.toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* BODY */}
      <div style={{ display:"flex", flex:1, overflow:"hidden", minHeight:0 }}>

        {/* LEFT PANEL */}
        <div style={{
          width:"280px", minWidth:"280px", flexShrink:0,
          background:"#060f1e", borderRight:"1px solid #0d2137",
          overflowY:"auto", padding:"12px",
        }}>
          <div style={{
            fontSize:"10px", color:"#2a7a9a", letterSpacing:"2px",
            marginBottom:"10px", paddingBottom:"8px",
            borderBottom:"1px solid #0d2137",
          }}>
            NODES: <span style={{ color:"#44ccff", fontWeight:700 }}>{nodes.length}</span>
            {"  |  "}f={Math.floor(((stats.healthy_count ?? nodes.length)-1)/3)}
            {"  |  "}Q:{stats.quorum === 0 ? "N/A" : (stats.quorum ?? Math.floor(nodes.length*0.67)+1)}
          </div>

          <SLabel>INJECT ATTACK</SLabel>
          {ATTACKS.map(({ label, desc, type, icon, color }) => (
            <button key={type} onClick={() => doAttack(type)}
              disabled={phase === "consensus" || !connected}
              style={{
                background:"#0a1628", border:`1px solid ${color}33`,
                borderLeft:`3px solid ${color}`, borderRadius:"8px", padding:"12px",
                cursor:(phase==="consensus"||!connected)?"not-allowed":"pointer",
                textAlign:"left", display:"flex", alignItems:"center", gap:10,
                marginBottom:8, width:"100%",
                opacity:(phase==="consensus"||!connected)?0.4:1,
                transition:"all 0.15s",
              }}
              onMouseEnter={e => {
                if (phase!=="consensus" && connected) {
                  e.currentTarget.style.background="#0d1f36";
                  e.currentTarget.style.boxShadow=`0 0 14px ${color}22`;
                }
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background="#0a1628";
                e.currentTarget.style.boxShadow="none";
              }}
            >
              <span style={{ fontSize:"22px" }}>{icon}</span>
              <div>
                <div style={{ color, fontSize:"12px", fontWeight:700 }}>{label}</div>
                <div style={{ color:"#4a7a9a", fontSize:"10px", marginTop:2 }}>{desc}</div>
              </div>
            </button>
          ))}

          <SLabel>RECOVERY</SLabel>

          {/* ── PAUSE / RESUME BUTTON ── */}
          <button
            onClick={doPause}
            style={{
              background: isPaused ? "#2a1a00" : "#071624",
              border: `2px solid ${isPaused ? "#ffaa00" : "#ffaa0055"}`,
              borderRadius: "8px",
              padding: "11px",
              color: isPaused ? "#ffaa00" : "#ffaa0099",
              fontSize: "12px",
              fontWeight: 800,
              cursor: "pointer",
              letterSpacing: "2px",
              marginBottom: 8,
              width: "100%",
              transition: "all 0.2s",
              fontFamily: "'Courier New',monospace",
              boxShadow: isPaused ? "0 0 18px #ffaa0033" : "none",
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = "#ffaa00";
              e.currentTarget.style.boxShadow   = "0 0 20px #ffaa0044";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = isPaused ? "#ffaa00" : "#ffaa0055";
              e.currentTarget.style.boxShadow   = isPaused ? "0 0 18px #ffaa0033" : "none";
            }}
          >
            {isPaused ? "▶  RESUME NETWORK" : "⏸  PAUSE NETWORK"}
          </button>

          {/* Status badge shown only when paused */}
          {isPaused && (
            <div style={{
              fontSize: "10px",
              color: "#ffaa00",
              background: "#ffaa0011",
              border: "1px solid #ffaa0033",
              borderRadius: "6px",
              padding: "6px 10px",
              marginBottom: 8,
              textAlign: "center",
              letterSpacing: "1px",
              fontWeight: 700,
            }}>
              ⚠ ALL COMMS SUSPENDED
            </div>
          )}

          <button onClick={doReset} style={{
            background:"#071624", border:"2px solid #44ccff55",
            borderRadius:"8px", padding:"11px", color:"#44ccff",
            fontSize:"12px", fontWeight:800, cursor:"pointer",
            letterSpacing:"2px", marginBottom:14, width:"100%",
            transition:"all 0.15s", fontFamily:"'Courier New',monospace",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.borderColor="#44ccff";
            e.currentTarget.style.boxShadow="0 0 20px #44ccff33";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor="#44ccff55";
            e.currentTarget.style.boxShadow="none";
          }}>
            ↺ RESET NETWORK
          </button>

          <SLabel>NETWORK STATS</SLabel>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:7 }}>
            {[
              { label:"HEALTHY",     value:healthy,                             color:"#00ff88" },
              { label:"QUARANTINED", value: nodes.filter(n=>n.status==="quarantined").length, color:"#ff9800" },
              { label:"BLOCKS",      value:stats.block_count?.toLocaleString(), color:"#44ccff" },
              { label:"TX/S",        value:stats.tx_rate,                       color:"#cc88ff" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{
                background:"#0a1628", border:"1px solid #0d2a40",
                borderRadius:8, padding:"11px", textAlign:"center",
              }}>
                <div style={{ fontSize:"22px", fontWeight:800, color, lineHeight:1,
                              textShadow:`0 0 10px ${color}88` }}>
                  {value}
                </div>
                <div style={{ fontSize:"9px", color:"#2a6a8a",
                              letterSpacing:"2px", marginTop:4, fontWeight:700 }}>
                  {label}
                </div>
              </div>
            ))}
          </div>

          <div style={{
            marginTop:10, background:"#0a1628",
            border:"1px solid #bb88ff33", borderRadius:8, padding:10,
          }}>
            <div style={{ fontSize:"10px", color:"#7755aa",
                          letterSpacing:"2px", marginBottom:7, fontWeight:700 }}>
              PRIMARY ROTATION
            </div>
            <div style={{ display:"flex", flexWrap:"wrap", gap:4 }}>
              {nodes.filter(n => n.status==="healthy").map(n => (
                <div key={n.id} style={{
                  fontSize:"10px", fontWeight:800, padding:"3px 7px", borderRadius:4,
                  background: n.is_primary ? "#bb88ff33" : "#0d1628",
                  color:      n.is_primary ? "#bb88ff"   : "#2a6a8a",
                  border:`1px solid ${n.is_primary ? "#bb88ff66" : "#0d2137"}`,
                  transition:"all 0.4s",
                }}>
                  {n.is_primary ? "▶ " : ""}{n.id}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* CENTRE — network graph */}
        <div style={{ flex:1, position:"relative", overflow:"hidden", minWidth:0 }}>
          <NetworkGraph
            nodes={nodes} edges={edges}
            selectedNode={selectedNode} onNodeClick={setSelectedNode}
          />
          {phase === "consensus" && (
            <div style={{
              position:"absolute", bottom:14, left:"50%",
              transform:"translateX(-50%)", width:420, zIndex:10,
            }}>
              <ConsensusBar votes={consensusVotes} nodes={nodes} />
            </div>
          )}
        </div>

        {/* NODE REGISTRY */}
        <div style={{
          width:"260px", minWidth:"260px", flexShrink:0,
          background:"#060f1e", borderLeft:"1px solid #0d2137",
          display:"flex", flexDirection:"column",
          overflow:"hidden", padding:"12px",
        }}>
          <SLabel>NODE REGISTRY</SLabel>

          <div style={{
            background:"#0a1628", border:"1px solid #0d2a40",
            borderRadius:8, padding:10, marginBottom:10,
          }}>
            <div style={{ fontSize:"10px", color:"#2a6a8a",
                          letterSpacing:"2px", marginBottom:6, fontWeight:700 }}>
              CONSENSUS ROUND
            </div>
            <div style={{ height:4, background:"#0d2137",
                          borderRadius:2, overflow:"hidden", marginBottom:6 }}>
              <div style={{
                height:"100%",
                width: phase==="idle"?"100%":phase==="consensus"?"55%":"25%",
                background:"linear-gradient(90deg,#00ff88,#00ddff)",
                transition:"width 0.5s",
              }} />
            </div>
            <div style={{ fontSize:"10px", color:"#00ff88",
                          letterSpacing:"2px", fontWeight:700 }}>
              {phase==="idle"?"● STABLE":phase==="consensus"?"◉ PBFT ACTIVE":"○ MONITORING"}
            </div>
          </div>

          <div style={{ flex:1, overflowY:"auto", display:"flex",
                        flexDirection:"column", gap:5 }}>
            {nodes.map(n => {
              const sc    = STATUS_COLOR[n.status] ?? "#44ccff";
              const isSel = selectedNode?.id === n.id;
              return (
                <div key={n.id}
                  onClick={() => setSelectedNode(isSel ? null : n)}
                  style={{
                    background:  isSel ? "#0d1f36" : "#0a1628",
                    border:      `1px solid ${isSel ? sc+"66" : "#0d2a40"}`,
                    borderLeft:  `4px solid ${sc}`,
                    borderRadius:6, padding:"9px 11px",
                    cursor:"pointer", transition:"all 0.2s",
                  }}
                  onMouseEnter={e=>{ if(!isSel) e.currentTarget.style.background="#0c1a2e"; }}
                  onMouseLeave={e=>{ if(!isSel) e.currentTarget.style.background="#0a1628"; }}
                >
                  <div style={{ display:"flex", justifyContent:"space-between",
                                alignItems:"center", marginBottom:5 }}>
                    <span style={{ color:"#fff", fontSize:"12px", fontWeight:800 }}>
                      {n.is_primary ? "🔄 " : ""}Node-{n.id.replace("N","")}
                    </span>
                    <span style={{
                      fontSize:"9px", fontWeight:800, padding:"2px 6px", borderRadius:4,
                      background:`${sc}22`, color:sc, border:`1px solid ${sc}44`,
                    }}>
                      {n.is_primary ? "PRIMARY" : n.status.toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between",
                                fontSize:"10px", color:"#4a8aaa",
                                marginBottom:5, fontWeight:600 }}>
                    <span>REP <span style={{
                      color:n.reputation>60?"#00ff88":"#ff4444", fontWeight:800,
                    }}>{Math.round(n.reputation)}%</span></span>
                    <span>BLK <span style={{ color:"#44ccff", fontWeight:800 }}>
                      {n.block_count}</span></span>
                    <span>P <span style={{ color:"#cc88ff", fontWeight:800 }}>
                      {n.connected_peers?.length??0}</span></span>
                  </div>
                  <div style={{ height:3, background:"#0d2137",
                                borderRadius:2, overflow:"hidden" }}>
                    <div style={{
                      height:"100%", width:`${n.reputation}%`,
                      background: n.reputation>60
                        ? "linear-gradient(90deg,#00ff88,#00ddff)"
                        : "linear-gradient(90deg,#ff4444,#ffaa00)",
                      transition:"width 0.4s",
                    }} />
                  </div>
                  {n.attack_type && (
                    <div style={{ marginTop:4, fontSize:"9px",
                                  color:"#ff4444", fontWeight:700 }}>
                      ⚠ {n.attack_type.toUpperCase()} DETECTED
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* METRICS PANEL */}
        {showMetrics && (
          <div style={{
            width:"300px", minWidth:"300px", flexShrink:0,
            background:"#060f1e", borderLeft:"1px solid #0d2137",
            overflow:"hidden", display:"flex", flexDirection:"column",
          }}>
            <MetricsPanel edgeMetrics={edgeMetrics} edges={edges} phase={phase} />
          </div>
        )}

        {/* GRAPHS PANEL */}
        {showGraphs && (
          <div style={{
            width:"320px", minWidth:"320px", flexShrink:0,
            borderLeft:"1px solid #0d2137",
            overflow:"hidden", display:"flex", flexDirection:"column",
          }}>
            <MetricsGraphs edgeMetrics={edgeMetrics} phase={phase} />
          </div>
        )}
      </div>

      {/* LOG */}
      <LogFeed logs={logs} />

      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.15} }
        ::-webkit-scrollbar { width:4px }
        ::-webkit-scrollbar-track { background:#040d18 }
        ::-webkit-scrollbar-thumb { background:#0d2a40; border-radius:3px }
        button:focus { outline:none }
        * { box-sizing:border-box }
      `}</style>
    </div>
  );
}