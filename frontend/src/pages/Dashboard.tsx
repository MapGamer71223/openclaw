import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ScanSearch, Zap, Bot, PenTool, ShieldCheck, HelpCircle, Globe2,
  ArrowRight, FolderSearch, Clock,
} from "lucide-react";
import { api } from "../services/api";
import type { Investigation } from "../types";
import { VerdictBadge, ConfidencePill, StatCard, EmptyState, Skeleton, StatusBadge } from "../components/ui";

function timeAgo(iso: string) {
  const d = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - d);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function InvestigationCard({ inv }: { inv: Investigation }) {
  const isProcessing = !["COMPLETED", "FAILED", "PARTIAL"].includes(inv.state);
  return (
    <Link
      to={`/investigations/${inv.id}`}
      className="panel panel-hover group p-4 flex flex-col gap-3 animate-slideUp focus-ring"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-forensic-muted mono truncate">{inv.id.slice(0, 8)}</div>
          <div className="text-sm font-semibold text-forensic-text truncate mt-0.5" title={inv.original_filename}>
            {inv.original_filename}
          </div>
        </div>
        <StatusBadge state={inv.state} />
      </div>

      {isProcessing ? (
        <div>
          <div className="h-1.5 bg-forensic-panel3 rounded-full overflow-hidden border border-forensic-border">
            <div className="h-full bg-gradient-to-r from-forensic-accent to-forensic-violet animate-pulseGlow rounded-full" style={{ width: "60%" }} />
          </div>
          <div className="text-[11px] text-forensic-muted mt-1.5">Analysis in progress…</div>
        </div>
      ) : inv.state === "FAILED" ? (
        <div className="text-xs text-forensic-danger">Investigation failed</div>
      ) : (
        <div className="flex items-center justify-between">
          <VerdictBadge verdict={inv.verdict} size="sm" />
          <ConfidencePill label={inv.confidence_label} />
        </div>
      )}

      <div className="flex items-center justify-between text-[11px] text-forensic-muted pt-2 border-t border-forensic-border/60">
        <span className="flex items-center gap-1"><Clock size={11} />{timeAgo(inv.created_at)}</span>
        <span className="flex items-center gap-1 text-forensic-accent group-hover:gap-1.5 transition-all">
          Open <ArrowRight size={12} />
        </span>
      </div>
    </Link>
  );
}

export function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.stats(), api.listInvestigations()])
      .then(([s, invs]) => { if (!cancelled) { setStats(s); setInvestigations(invs); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const STAT_CARDS = stats
    ? [
        { label: "Total Investigations", value: stats.total_investigations, icon: FolderSearch, accent: "text-forensic-text" },
        { label: "AI-Generated", value: stats.ai_generated, icon: Bot, accent: "text-forensic-danger" },
        { label: "AI-Altered", value: stats.ai_altered, icon: PenTool, accent: "text-forensic-warn" },
        { label: "Authentic", value: stats.authentic, icon: ShieldCheck, accent: "text-forensic-success" },
        { label: "Inconclusive", value: stats.inconclusive, icon: HelpCircle, accent: "text-forensic-muted" },
        { label: "Sources Traced", value: stats.sources_traced, icon: Globe2, accent: "text-forensic-accent" },
      ]
    : [];

  return (
    <div className="p-5 sm:p-8 max-w-6xl mx-auto">
      {/* Hero */}
      <div className="relative panel overflow-hidden p-7 sm:p-10 mb-8 animate-fadeIn">
        <div className="absolute inset-0 grid-texture pointer-events-none" />
        <div className="relative">
          <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-forensic-accent uppercase tracking-wider mb-3">
            <ScanSearch size={14} /> Investigate · Analyze · Verify · Trace · Report
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-forensic-text tracking-tight mb-2">
            Media Forensics <span className="text-gradient">Command Center</span>
          </h1>
          <p className="text-sm sm:text-[15px] text-forensic-muted max-w-xl mb-6">
            Investigate authenticity, detect manipulation, and trace media origins across the web.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/upload"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-forensic-accent text-forensic-bg font-semibold text-sm hover:brightness-110 transition shadow-glow"
            >
              <ScanSearch size={16} /> + New Investigation
            </Link>
            <Link
              to="/upload"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg border border-forensic-border text-forensic-text2 font-semibold text-sm hover:border-forensic-accent/40 hover:text-forensic-text transition"
            >
              <Zap size={16} /> Quick Check
            </Link>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
        {loading
          ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[84px]" />)
          : STAT_CARDS.map((s) => <StatCard key={s.label} {...s} />)}
      </div>

      {/* Recent investigations */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-forensic-muted">Recent Investigations</h2>
        {investigations.length > 0 && (
          <span className="text-xs text-forensic-muted mono">{investigations.length} total</span>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[140px]" />)}
        </div>
      ) : investigations.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={FolderSearch}
            title="No investigations yet"
            subtitle="Start your first forensic investigation, or run the bundled offline demo to see the platform in action."
            action={
              <Link to="/upload" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-forensic-accent text-forensic-bg font-semibold text-sm hover:brightness-110 transition">
                <ScanSearch size={15} /> Start an Investigation
              </Link>
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {investigations.map((inv) => <InvestigationCard key={inv.id} inv={inv} />)}
        </div>
      )}
    </div>
  );
}
