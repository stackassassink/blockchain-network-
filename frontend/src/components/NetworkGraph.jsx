import { useEffect, useRef } from "react";
import * as d3 from "d3";

const STATUS_COLOR = {
  healthy:     "#00ff88",
  compromised: "#ff4444",
  quarantined: "#ff6600",
  suspect:     "#ffee00",
  healing:     "#00ddff",
  primary:     "#bb88ff",
};

// Fixed positions for a clean, readable partial-mesh layout
// Sized for a ~800×600 viewport — D3 will scale to actual size
const FIXED_POSITIONS = {
  N1: { x: 0.50, y: 0.42 },  // centre
  N2: { x: 0.25, y: 0.25 },  // top-left
  N3: { x: 0.72, y: 0.18 },  // top-right
  N4: { x: 0.28, y: 0.68 },  // bottom-left
  N5: { x: 0.55, y: 0.72 },  // bottom-centre
  N6: { x: 0.75, y: 0.50 },  // right
  N7: { x: 0.42, y: 0.85 },  // bottom
};

const EDGES = [
  ["N1","N2"],["N1","N3"],["N1","N4"],
  ["N2","N3"],["N2","N5"],
  ["N3","N6"],
  ["N4","N5"],["N4","N7"],
  ["N5","N6"],
  ["N6","N7"],
];

export default function NetworkGraph({ nodes=[], edges=[], selectedNode, onNodeClick }) {
  const svgRef      = useRef(null);
  const gRef        = useRef(null);
  const nodeEls     = useRef({});
  const edgeEls     = useRef({});
  const pulseEls    = useRef({});
  const labelEls    = useRef({});
  const repBarEls   = useRef({});
  const initDone    = useRef(false);

  // ── Build once ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!svgRef.current || initDone.current) return;
    initDone.current = true;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const W = svgRef.current.clientWidth  || 800;
    const H = svgRef.current.clientHeight || 600;

    // Defs — glow filters + arrow marker
    const defs = svg.append("defs");

    // Green glow
    const glowGreen = defs.append("filter").attr("id","glow-green").attr("x","-50%").attr("y","-50%").attr("width","200%").attr("height","200%");
    glowGreen.append("feGaussianBlur").attr("stdDeviation","4").attr("result","blur");
    const mgGreen = glowGreen.append("feMerge");
    mgGreen.append("feMergeNode").attr("in","blur");
    mgGreen.append("feMergeNode").attr("in","SourceGraphic");

    // Red glow
    const glowRed = defs.append("filter").attr("id","glow-red").attr("x","-50%").attr("y","-50%").attr("width","200%").attr("height","200%");
    glowRed.append("feGaussianBlur").attr("stdDeviation","6").attr("result","blur");
    const mgRed = glowRed.append("feMerge");
    mgRed.append("feMergeNode").attr("in","blur");
    mgRed.append("feMergeNode").attr("in","SourceGraphic");

    // Pulse glow
    const glowPulse = defs.append("filter").attr("id","glow-pulse").attr("x","-80%").attr("y","-80%").attr("width","360%").attr("height","360%");
    glowPulse.append("feGaussianBlur").attr("stdDeviation","8").attr("result","blur");
    const mgPulse = glowPulse.append("feMerge");
    mgPulse.append("feMergeNode").attr("in","blur");
    mgPulse.append("feMergeNode").attr("in","SourceGraphic");

    // Background grid
    const gridG = svg.append("g").attr("class","grid");
    const gridSize = 40;
    for (let x = 0; x < W; x += gridSize) {
      gridG.append("line")
        .attr("x1",x).attr("y1",0).attr("x2",x).attr("y2",H)
        .attr("stroke","#0a1e30").attr("stroke-width",0.5);
    }
    for (let y = 0; y < H; y += gridSize) {
      gridG.append("line")
        .attr("x1",0).attr("y1",y).attr("x2",W).attr("y2",y)
        .attr("stroke","#0a1e30").attr("stroke-width",0.5);
    }

    // Main group (zoom target)
    const g = svg.append("g").attr("class","main");
    gRef.current = g;

    // Zoom
    const zoom = d3.zoom()
      .scaleExtent([0.3, 4])
      .on("zoom", e => g.attr("transform", e.transform));
    svg.call(zoom);

    // Double-click to reset zoom
    svg.on("dblclick.zoom", () => {
      svg.transition().duration(500)
        .call(zoom.transform, d3.zoomIdentity);
    });

    // ── Compute fixed positions ──────────────────────────────────────────
    const pos = {};
    Object.entries(FIXED_POSITIONS).forEach(([id, frac]) => {
      pos[id] = { x: frac.x * W, y: frac.y * H };
    });

    // ── Draw edges ───────────────────────────────────────────────────────
    const edgeG = g.append("g").attr("class","edges");

    EDGES.forEach(([a, b]) => {
      const key = `${a}-${b}`;
      const pa  = pos[a];
      const pb  = pos[b];
      if (!pa || !pb) return;

      // Glow line (thick, low opacity)
      edgeG.append("line")
        .attr("class", `edge-glow edge-glow-${key}`)
        .attr("x1", pa.x).attr("y1", pa.y)
        .attr("x2", pb.x).attr("y2", pb.y)
        .attr("stroke", "#00ff88")
        .attr("stroke-width", 6)
        .attr("opacity", 0.06)
        .attr("stroke-linecap","round");

      // Main line
      const line = edgeG.append("line")
        .attr("class", `edge-line edge-line-${key}`)
        .attr("x1", pa.x).attr("y1", pa.y)
        .attr("x2", pb.x).attr("y2", pb.y)
        .attr("stroke", "#0d4a6a")
        .attr("stroke-width", 1.5)
        .attr("stroke-linecap","round");

      edgeEls.current[key] = line.node();

      // Animated packet dot
      const dot = edgeG.append("circle")
        .attr("class", `packet-dot packet-dot-${key}`)
        .attr("r", 3)
        .attr("fill", "#44ccff")
        .attr("opacity", 0)
        .attr("cx", pa.x).attr("cy", pa.y);

      pulseEls.current[key] = { dot: dot.node(), pa, pb };
    });

    // ── Draw nodes ───────────────────────────────────────────────────────
    const nodeG = g.append("g").attr("class","nodes");

    const nodeIds = ["N1","N2","N3","N4","N5","N6","N7"];
    nodeIds.forEach(id => {
      const p = pos[id];
      if (!p) return;

      const ng = nodeG.append("g")
        .attr("class", `node-group node-${id}`)
        .attr("transform", `translate(${p.x},${p.y})`)
        .attr("cursor","pointer")
        .on("click", () => {
          const liveNode = nodes.find(n => n.id === id);
          onNodeClick?.(liveNode ?? { id });
        });

      // Outer pulse ring (animated for compromised/primary)
      ng.append("circle")
        .attr("class","pulse-ring")
        .attr("r", 32)
        .attr("fill","none")
        .attr("stroke","#00ff88")
        .attr("stroke-width", 1)
        .attr("opacity", 0);

      // Shadow circle
      ng.append("circle")
        .attr("class","node-shadow")
        .attr("r", 26)
        .attr("fill","#000")
        .attr("opacity", 0.5)
        .attr("filter","url(#glow-green)");

      // Main circle
      ng.append("circle")
        .attr("class","node-body")
        .attr("r", 24)
        .attr("fill","#060f1e")
        .attr("stroke","#00ff88")
        .attr("stroke-width", 2.5);

      // Inner circle accent
      ng.append("circle")
        .attr("class","node-inner")
        .attr("r", 18)
        .attr("fill","none")
        .attr("stroke","#00ff88")
        .attr("stroke-width", 0.5)
        .attr("opacity", 0.3);

      // ID label
      ng.append("text")
        .attr("class","node-label")
        .attr("text-anchor","middle")
        .attr("dy","-0.1em")
        .attr("fill","#ffffff")
        .attr("font-size","13px")
        .attr("font-family","'Courier New',monospace")
        .attr("font-weight","bold")
        .attr("pointer-events","none")
        .text(id);

      // Status label below ID
      const statusText = ng.append("text")
        .attr("class","node-status-text")
        .attr("text-anchor","middle")
        .attr("dy","1.1em")
        .attr("fill","#00ff88")
        .attr("font-size","8px")
        .attr("font-family","'Courier New',monospace")
        .attr("font-weight","700")
        .attr("pointer-events","none")
        .attr("letter-spacing","1px")
        .text("HEALTHY");

      labelEls.current[id] = statusText.node();

      // Reputation bar below node
      const barW = 36;
      ng.append("rect")
        .attr("x", -barW/2).attr("y", 28)
        .attr("width", barW).attr("height", 3)
        .attr("rx", 1.5)
        .attr("fill","#0d2137");

      const repBar = ng.append("rect")
        .attr("class","rep-bar")
        .attr("x", -barW/2).attr("y", 28)
        .attr("width", barW).attr("height", 3)
        .attr("rx", 1.5)
        .attr("fill","#00ff88");

      repBarEls.current[id] = { el: repBar.node(), barW };

      nodeEls.current[id] = ng.node();
    });

    // Start packet animations
    animatePackets(pos);

  }, []); // runs once

  // ── Packet animation ──────────────────────────────────────────────────────
  function animatePackets(pos) {
    const animate = (key, pa, pb) => {
      const dot = d3.select(pulseEls.current[key]?.dot);
      if (!dot || dot.empty()) return;

      // Check if edge is active
      const edgeEl = edgeEls.current[key];
      const isActive = edgeEl
        ? !d3.select(edgeEl).attr("stroke-dasharray")
        : true;

      if (!isActive) {
        setTimeout(() => animate(key, pa, pb), 3000);
        return;
      }

      const dur = 1200 + Math.random() * 1800;
      dot
        .attr("cx", pa.x).attr("cy", pa.y)
        .attr("opacity", 0)
        .transition().duration(200)
        .attr("opacity", 0.9)
        .transition().duration(dur)
        .ease(d3.easeLinear)
        .attr("cx", pb.x).attr("cy", pb.y)
        .transition().duration(200)
        .attr("opacity", 0)
        .on("end", () => {
          setTimeout(() => animate(key, pb, pa), 400 + Math.random() * 1200);
        });
    };

    Object.entries(pulseEls.current).forEach(([key, { dot, pa, pb }]) => {
      setTimeout(() => animate(key, pa, pb), Math.random() * 2000);
    });
  }

  // ── Update on data change ─────────────────────────────────────────────────
  useEffect(() => {
    if (!initDone.current || !gRef.current) return;
    if (!nodes.length) return;

    const svg = d3.select(svgRef.current);
    const g   = gRef.current;

    nodes.forEach(n => {
      const ng = d3.select(nodeEls.current[n.id]);
      if (ng.empty()) return;

      const color = n.is_primary
        ? "#bb88ff"
        : STATUS_COLOR[n.status] ?? "#00ff88";

      const isCompromised  = n.status === "compromised";
      const isQuarantined  = n.status === "quarantined";
      const isPrimary      = n.is_primary;

      // Node body stroke + fill
      ng.select(".node-body")
        .transition().duration(400)
        .attr("stroke", color)
        .attr("stroke-width", isPrimary ? 3.5 : isCompromised ? 3 : 2.5)
        .attr("fill", isQuarantined ? "#1a0800" : isCompromised ? "#1a0000" : "#060f1e");

      // Inner ring
      ng.select(".node-inner")
        .transition().duration(400)
        .attr("stroke", color)
        .attr("opacity", isPrimary ? 0.6 : 0.25);

      // Shadow / glow
      ng.select(".node-shadow")
        .attr("fill", color)
        .attr("filter", isCompromised || isQuarantined ? "url(#glow-red)" : "url(#glow-green)");

      // Pulse ring — animate for compromised/primary
      const ring = ng.select(".pulse-ring");
      ring.attr("stroke", color);
      if (isCompromised || isPrimary) {
        ring.attr("opacity", 0.4)
          .transition().duration(800).ease(d3.easeLinear)
          .attr("r", 36).attr("opacity", 0)
          .on("end", function() {
            d3.select(this).attr("r", 28);
          });
      } else {
        ring.attr("opacity", 0).attr("r", 32);
      }

      // Status text
      const statusLabel = isQuarantined ? "QUARANTINED"
                        : isCompromised  ? n.attack_type?.toUpperCase() ?? "ATTACK"
                        : isPrimary      ? "PRIMARY"
                        : "HEALTHY";

      d3.select(labelEls.current[n.id])
        .text(statusLabel)
        .attr("fill", color)
        .attr("font-size", isQuarantined ? "7px" : "8px");

      // Rep bar
      const rb = repBarEls.current[n.id];
      if (rb) {
        const repFrac  = (n.reputation ?? 100) / 100;
        const barColor = repFrac > 0.6 ? "#00ff88"
                       : repFrac > 0.3 ? "#ff9800" : "#ff3333";
        d3.select(rb.el)
          .transition().duration(400)
          .attr("width", rb.barW * repFrac)
          .attr("fill", barColor);
      }

      // Selected highlight
      ng.select(".node-body")
        .attr("stroke-width",
          selectedNode?.id === n.id ? 4 : isPrimary ? 3.5 : 2.5
        );
    });

    // Update edges
    edges.forEach(e => {
      const key = `${e.source}-${e.target}`;
      const el  = edgeEls.current[key];
      const gl  = svg.select(`.edge-glow-${key}`);

      if (!el) return;
      const line = d3.select(el);

      if (e.active) {
        // Find source/target node status
        const srcNode = nodes.find(n => n.id === e.source);
        const tgtNode = nodes.find(n => n.id === e.target);
        const isNearAttack = srcNode?.status === "compromised"
                          || tgtNode?.status === "compromised";

        line
          .transition().duration(300)
          .attr("stroke", isNearAttack ? "#ff440088" : "#1a6a9a")
          .attr("stroke-width", isNearAttack ? 2.5 : 1.5)
          .attr("stroke-dasharray", null)
          .attr("opacity", 1);

        gl.transition().duration(300)
          .attr("stroke", isNearAttack ? "#ff4400" : "#00ff88")
          .attr("opacity", isNearAttack ? 0.12 : 0.06);

      } else {
        // Severed edge
        line
          .transition().duration(300)
          .attr("stroke", "#ff440044")
          .attr("stroke-width", 1)
          .attr("stroke-dasharray", "6 5")
          .attr("opacity", 0.4);

        gl.transition().duration(300)
          .attr("opacity", 0);
      }
    });

  }, [nodes, edges, selectedNode]);

  return (
    <svg
      ref={svgRef}
      style={{
        width:"100%", height:"100%",
        background:"#050d1a",
        cursor:"grab",
      }}
    />
  );
}