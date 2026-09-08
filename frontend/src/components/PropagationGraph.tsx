import React, { useMemo, useRef, useState } from "react";
import { ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import type { GraphNode, GraphEdge } from "../types";

const TYPE_COLOR: Record<string, string> = {
  source: "#34D399",
  post: "#38BDF8",
  article: "#F59E0B",
  media: "#F43F5E",
};

const TYPE_LABEL: Record<string, string> = {
  source: "Source",
  post: "Social Post",
  article: "Article",
  media: "Media",
};

export function PropagationGraph({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragging = useRef<{ x: number; y: number } | null>(null);

  const layout = useMemo(() => {
    const width = 760, height = 60 + Math.max(1, nodes.length - 1) * 90 + 60;
    const positions: Record<string, { x: number; y: number }> = {};
    nodes.forEach((n, i) => {
      const isRoot = n.type === "source";
      positions[n.id] = isRoot ? { x: 80, y: height / 2 } : { x: 380 + (i % 2 === 0 ? 0 : 160), y: 60 + i * 80 };
    });
    return { width, height, positions };
  }, [nodes]);

  const legendTypes = useMemo(() => {
    const seen = new Set(nodes.map((n) => n.type));
    return Array.from(seen);
  }, [nodes]);

  if (!nodes.length) {
    return <div className="text-forensic-muted text-sm mono py-8 text-center">No propagation data available.</div>;
  }

  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }); };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.min(2.5, Math.max(0.5, z - e.deltaY * 0.001)));
  };
  const onMouseDown = (e: React.MouseEvent) => { dragging.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }; };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragging.current) return;
    setPan({ x: e.clientX - dragging.current.x, y: e.clientY - dragging.current.y });
  };
  const onMouseUp = () => { dragging.current = null; };

  return (
    <div className="flex flex-col lg:flex-row gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-2">
          <div className="flex flex-wrap gap-3">
            {legendTypes.map((t) => (
              <span key={t} className="flex items-center gap-1.5 text-[11px] text-forensic-muted">
                <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: TYPE_COLOR[t] || "#7A869E" }} />
                {TYPE_LABEL[t] || t}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))} className="p-1.5 rounded-md border border-forensic-border text-forensic-muted hover:text-forensic-text hover:border-forensic-accent/40 transition focus-ring" aria-label="Zoom in">
              <ZoomIn size={14} />
            </button>
            <button onClick={() => setZoom((z) => Math.max(0.5, z - 0.2))} className="p-1.5 rounded-md border border-forensic-border text-forensic-muted hover:text-forensic-text hover:border-forensic-accent/40 transition focus-ring" aria-label="Zoom out">
              <ZoomOut size={14} />
            </button>
            <button onClick={resetView} className="p-1.5 rounded-md border border-forensic-border text-forensic-muted hover:text-forensic-text hover:border-forensic-accent/40 transition focus-ring" aria-label="Reset view">
              <RotateCcw size={14} />
            </button>
          </div>
        </div>
        <div
          className="rounded-lg border border-forensic-border bg-forensic-panel3/40 overflow-hidden cursor-grab active:cursor-grabbing"
          style={{ height: 420 }}
          onWheel={onWheel}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
        >
          <svg
            width="100%"
            height="100%"
            viewBox={`0 0 ${layout.width} ${layout.height}`}
          >
            <g style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "center" }}>
              {edges.map((e, i) => {
                const from = layout.positions[e.from];
                const to = layout.positions[e.to];
                if (!from || !to) return null;
                return (
                  <g key={i}>
                    <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} style={{ stroke: "rgb(var(--f-border2))" }} strokeWidth={1.5} />
                    <text
                      x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 4}
                      style={{ fill: "rgb(var(--f-muted))" }} fontSize="9" fontFamily="JetBrains Mono, monospace" textAnchor="middle"
                    >
                      {e.type}
                    </text>
                  </g>
                );
              })}
              {nodes.map((n) => {
                const p = layout.positions[n.id];
                if (!p) return null;
                const color = TYPE_COLOR[n.type] || "#7A869E";
                const isSelected = selected?.id === n.id;
                return (
                  <g key={n.id} onClick={() => setSelected(n)} className="cursor-pointer">
                    <circle
                      cx={p.x} cy={p.y} r={n.type === "source" ? 22 : 16}
                      style={{ fill: "rgb(var(--f-panel))" }} stroke={color} strokeWidth={isSelected ? 3 : 2}
                    />
                    <text x={p.x} y={p.y + 4} fill={color} fontSize="9" fontFamily="JetBrains Mono, monospace" textAnchor="middle" fontWeight="bold">
                      {n.type.slice(0, 3).toUpperCase()}
                    </text>
                    <text x={p.x} y={p.y + (n.type === "source" ? 38 : 32)} style={{ fill: "rgb(var(--f-text))" }} fontSize="10" textAnchor="middle">
                      {n.platform || n.type}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        </div>
      </div>
      <div className="w-full lg:w-64 flex-shrink-0">
        {selected ? (
          <div className="panel p-3.5 text-xs space-y-2 animate-scaleIn">
            <div className="font-semibold text-forensic-text text-sm">{selected.platform || selected.type}</div>
            <a href={selected.url} target="_blank" rel="noreferrer" className="text-forensic-muted break-all hover:text-forensic-accent block">{selected.url}</a>
            <div className="pt-2 border-t border-forensic-border/60 space-y-1.5">
              <div className="flex justify-between"><span className="text-forensic-muted">Timestamp</span><span className="mono">{selected.timestamp ? new Date(selected.timestamp).toLocaleString() : "unknown"}</span></div>
              <div className="flex justify-between"><span className="text-forensic-muted">Similarity</span><span className="mono">{selected.similarity_score != null ? `${Math.round(selected.similarity_score * 100)}%` : "N/A"}</span></div>
              <div className="flex justify-between"><span className="text-forensic-muted">Confidence</span><span className="mono">{selected.evidence_confidence != null ? `${Math.round(selected.evidence_confidence * 100)}%` : "N/A"}</span></div>
            </div>
          </div>
        ) : (
          <div className="text-forensic-muted text-xs italic py-4 text-center lg:text-left">Click a node to see its details.</div>
        )}
      </div>
    </div>
  );
}
