import React, { useState } from "react";
import {
  ShieldAlert, ShieldCheck, ShieldQuestion, AlertTriangle, Copy, Check,
  Sparkles,
} from "lucide-react";

/* ---------------------------------------------------------------------- */
/* Verdict + confidence                                                    */
/* ---------------------------------------------------------------------- */

const VERDICT_MAP: Record<string, { label: string; cls: string; icon: React.ElementType; ring: string }> = {
  AI_GENERATED: { label: "AI-Generated", cls: "bg-forensic-danger/10 text-forensic-danger border-forensic-danger/30", icon: ShieldAlert, ring: "shadow-[0_0_0_1px_rgba(244,63,94,0.25)]" },
  AI_ALTERED: { label: "Likely AI-Altered", cls: "bg-forensic-warn/10 text-forensic-warn border-forensic-warn/30", icon: AlertTriangle, ring: "shadow-[0_0_0_1px_rgba(245,158,11,0.25)]" },
  LIKELY_AUTHENTIC: { label: "Likely Authentic", cls: "bg-forensic-success/10 text-forensic-success border-forensic-success/30", icon: ShieldCheck, ring: "shadow-[0_0_0_1px_rgba(52,211,153,0.25)]" },
  INCONCLUSIVE: { label: "Inconclusive", cls: "bg-forensic-muted/10 text-forensic-muted border-forensic-muted/30", icon: ShieldQuestion, ring: "" },
};

export function VerdictBadge({ verdict, size = "md" }: { verdict: string | null; size?: "sm" | "md" | "lg" }) {
  const v = (verdict && VERDICT_MAP[verdict]) || { label: verdict || "Pending", cls: "bg-forensic-muted/10 text-forensic-muted border-forensic-muted/30", icon: ShieldQuestion, ring: "" };
  const Icon = v.icon;
  const sizeCls = size === "lg" ? "px-4 py-2 text-base" : size === "sm" ? "px-2 py-1 text-[11px]" : "px-3 py-1.5 text-sm";
  const iconSize = size === "lg" ? 18 : 14;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg border font-semibold tracking-wide ${v.cls} ${sizeCls} ${v.ring}`}>
      <Icon size={iconSize} strokeWidth={2.25} />
      {v.label}
    </span>
  );
}

export function ConfidencePill({ label }: { label: string | null }) {
  const colors: Record<string, string> = {
    HIGH: "text-forensic-danger", MEDIUM: "text-forensic-warn",
    LOW: "text-forensic-accent", INCONCLUSIVE: "text-forensic-muted",
  };
  return <span className={`mono text-xs font-semibold ${colors[label || ""] || "text-forensic-muted"}`}>{label || "—"}</span>;
}

export function ScoreBar({ label, value, colorClass = "bg-forensic-accent" }: { label: string; value: number | null; colorClass?: string }) {
  const pct = value != null ? Math.round(value * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-forensic-text2">{label}</span>
        <span className="mono text-forensic-text font-medium">{value != null ? `${pct}%` : "N/A"}</span>
      </div>
      <div className="h-2 bg-forensic-panel3 rounded-full overflow-hidden border border-forensic-border">
        <div className={`h-full ${colorClass} rounded-full transition-all duration-700 ease-out`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function ConfidenceGauge({ value, label }: { value: number | null; label?: string }) {
  const pct = value != null ? Math.round(value * 100) : 0;
  const r = 42, c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  const color = pct >= 70 ? "#F43F5E" : pct >= 40 ? "#F59E0B" : "#34D399";
  return (
    <div className="flex flex-col items-center justify-center">
      <div className="relative w-28 h-28">
        <svg viewBox="0 0 100 100" className="w-28 h-28 -rotate-90">
          <circle cx="50" cy="50" r={r} fill="none" style={{ stroke: "rgb(var(--f-border2))" }} strokeWidth="8" />
          <circle
            cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={value != null ? offset : c}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-forensic-text mono">{value != null ? `${pct}%` : "—"}</span>
        </div>
      </div>
      {label && <div className="text-[11px] uppercase tracking-wider text-forensic-muted mt-2">{label}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Structural                                                              */
/* ---------------------------------------------------------------------- */

export function Card({ title, children, className = "", right }: { title?: string; children: React.ReactNode; className?: string; right?: React.ReactNode }) {
  return (
    <div className={`panel p-5 ${className}`}>
      {(title || right) && (
        <div className="flex items-center justify-between mb-4">
          {title && <h3 className="text-xs font-semibold uppercase tracking-wider text-forensic-muted">{title}</h3>}
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

export function SectionHeader({ eyebrow, title, subtitle, right }: { eyebrow?: string; title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        {eyebrow && <div className="text-xs font-semibold uppercase tracking-wider text-forensic-accent mb-1">{eyebrow}</div>}
        <h1 className="text-2xl font-bold text-forensic-text tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-forensic-muted mt-1.5 max-w-xl">{subtitle}</p>}
      </div>
      {right && <div className="flex-shrink-0">{right}</div>}
    </div>
  );
}

export function DemoTag() {
  return (
    <span className="inline-flex items-center gap-1 mono text-[10px] px-1.5 py-0.5 rounded bg-forensic-warn/10 text-forensic-warn border border-forensic-warn/30 uppercase tracking-wider">
      <Sparkles size={10} /> Demo
    </span>
  );
}

export function StatusBadge({ state }: { state: string }) {
  const map: Record<string, string> = {
    COMPLETED: "bg-forensic-success/10 text-forensic-success border-forensic-success/30",
    FAILED: "bg-forensic-danger/10 text-forensic-danger border-forensic-danger/30",
    PARTIAL: "bg-forensic-warn/10 text-forensic-warn border-forensic-warn/30",
  };
  const cls = map[state] || "bg-forensic-accent/10 text-forensic-accent border-forensic-accent/30";
  const isProcessing = !map[state];
  return (
    <span className={`inline-flex items-center gap-1.5 mono text-[11px] px-2 py-1 rounded-md border font-medium ${cls}`}>
      {isProcessing && <span className="w-1.5 h-1.5 rounded-full bg-current pulse-dot" />}
      {state}
    </span>
  );
}

export function HashDisplay({ label, value }: { label: string; value: string | null | undefined }) {
  const [copied, setCopied] = useState(false);
  if (!value) {
    return (
      <div className="flex justify-between text-xs py-1.5">
        <span className="text-forensic-muted">{label}</span>
        <span className="mono text-forensic-faint">—</span>
      </div>
    );
  }
  const short = value.length > 22 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
  };
  return (
    <div className="flex items-center justify-between gap-3 text-xs py-1.5 border-b border-forensic-border/40 last:border-0">
      <span className="text-forensic-muted flex-shrink-0">{label}</span>
      <div className="flex items-center gap-2 min-w-0">
        <span className="mono text-forensic-text truncate" title={value}>{short}</span>
        <button
          onClick={copy}
          aria-label={`Copy ${label}`}
          className="flex-shrink-0 p-1 rounded text-forensic-muted hover:text-forensic-accent hover:bg-forensic-panel3 transition-colors focus-ring"
        >
          {copied ? <Check size={12} className="text-forensic-success" /> : <Copy size={12} />}
        </button>
      </div>
    </div>
  );
}

export function StatCard({ label, value, icon: Icon, accent = "text-forensic-text" }: { label: string; value: React.ReactNode; icon?: React.ElementType; accent?: string }) {
  return (
    <div className="panel panel-hover p-4">
      <div className="flex items-center justify-between mb-2">
        {Icon && <Icon size={16} className={accent} strokeWidth={2.25} />}
      </div>
      <div className={`text-2xl font-bold mono ${accent}`}>{value ?? "—"}</div>
      <div className="text-[11px] text-forensic-muted mt-1 leading-tight">{label}</div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, subtitle, action }: { icon?: React.ElementType; title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6">
      {Icon && (
        <div className="w-12 h-12 rounded-xl bg-forensic-panel3 border border-forensic-border flex items-center justify-center mb-4 text-forensic-muted">
          <Icon size={22} strokeWidth={1.75} />
        </div>
      )}
      <div className="text-sm font-semibold text-forensic-text2">{title}</div>
      {subtitle && <div className="text-xs text-forensic-muted mt-1.5 max-w-sm">{subtitle}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}
