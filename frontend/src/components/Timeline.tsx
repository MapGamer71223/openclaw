import React from "react";
import { Globe } from "lucide-react";

export function Timeline({ items }: { items: { url: string; platform: string | null; date: string | null; confidence: number | null }[] }) {
  if (!items.length) {
    return <div className="text-forensic-muted text-sm mono py-8 text-center">No timeline data available.</div>;
  }
  return (
    <div className="relative pl-7">
      <div className="absolute left-[9px] top-2 bottom-2 w-px bg-gradient-to-b from-forensic-accent/60 via-forensic-border to-forensic-border" />
      <div className="space-y-6">
        {items.map((item, i) => (
          <div key={i} className="relative animate-slideUp" style={{ animationDelay: `${i * 60}ms` }}>
            <div
              className={`absolute -left-7 top-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                i === 0 ? "bg-forensic-accent border-forensic-accent shadow-glow" : "bg-forensic-panel border-forensic-border"
              }`}
            >
              {i === 0 && <span className="w-1.5 h-1.5 rounded-full bg-forensic-bg" />}
            </div>
            <div className="panel p-3.5 panel-hover">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="mono text-xs text-forensic-accent font-medium">{item.date || "unknown date"}</span>
                {item.confidence != null && (
                  <span className="mono text-[11px] text-forensic-muted">{Math.round(item.confidence * 100)}% confidence</span>
                )}
              </div>
              <div className="flex items-center gap-1.5 text-sm font-medium text-forensic-text">
                <Globe size={13} className="text-forensic-muted flex-shrink-0" />
                {item.platform || "Unknown platform"}
              </div>
              <a href={item.url} target="_blank" rel="noreferrer" className="text-xs text-forensic-muted break-all hover:text-forensic-accent transition-colors block mt-1">
                {item.url}
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
