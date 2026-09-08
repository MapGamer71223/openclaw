import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  LayoutDashboard, Bot, Microscope, Archive, Globe2, History, GitBranch,
  FileText, AlertTriangle, RefreshCw, ShieldAlert, ExternalLink, Info,
} from "lucide-react";
import { api } from "../services/api";
import type { InvestigationDetail, Report, GraphNode, GraphEdge, SourceItem } from "../types";
import {
  VerdictBadge, ConfidencePill, ConfidenceGauge, ScoreBar, Card, DemoTag,
  HashDisplay, EmptyState, Skeleton, SectionHeader,
} from "../components/ui";
import { StatusPipeline } from "../components/StatusPipeline";
import { PropagationGraph } from "../components/PropagationGraph";
import { Timeline } from "../components/Timeline";

const TABS = [
  { key: "Overview", icon: LayoutDashboard },
  { key: "AI Detection", icon: Bot },
  { key: "Forensics", icon: Microscope },
  { key: "Evidence", icon: Archive },
  { key: "Sources", icon: Globe2 },
  { key: "Timeline", icon: History },
  { key: "Propagation", icon: GitBranch },
  { key: "Report", icon: FileText },
];

type AsyncState<T> = { data: T | null; status: "idle" | "loading" | "ready" | "error" };

function sleep(ms: number) { return new Promise((r) => setTimeout(r, ms)); }

export function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const [inv, setInv] = useState<InvestigationDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = useState("Overview");

  const [report, setReport] = useState<AsyncState<Report>>({ data: null, status: "idle" });
  const [graph, setGraph] = useState<AsyncState<{ nodes: GraphNode[]; edges: GraphEdge[] }>>({ data: null, status: "idle" });
  const [timeline, setTimeline] = useState<AsyncState<any[]>>({ data: null, status: "idle" });

  const [finalizing, setFinalizing] = useState(false);
  const [finalizingSlow, setFinalizingSlow] = useState(false);
  const completingRef = useRef(false);

  const fetchSecondaryData = useCallback((invId: string) => {
    setReport({ data: null, status: "loading" });
    api.getReport(invId).then((r) => setReport({ data: r, status: "ready" })).catch(() => setReport({ data: null, status: "error" }));
    setGraph({ data: null, status: "loading" });
    api.getGraph(invId).then((g) => setGraph({ data: g, status: "ready" })).catch(() => setGraph({ data: null, status: "error" }));
    setTimeline({ data: null, status: "loading" });
    api.getTimeline(invId).then((t) => setTimeline({ data: t, status: "ready" })).catch(() => setTimeline({ data: null, status: "error" }));
  }, []);

  // Initial load
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    api.getInvestigation(id).then((detail) => {
      if (cancelled) return;
      setInv(detail);
      if (detail.state === "COMPLETED") fetchSecondaryData(id);
    }).catch(() => { if (!cancelled) setNotFound(true); });
    return () => { cancelled = true; };
  }, [id, fetchSecondaryData]);

  // Robust completion handling: called once the live pipeline reports the
  // investigation is finished. The backend may briefly still return a
  // stale (non-terminal) investigation record, so we re-fetch with retries
  // rather than trusting a single request.
  const handleWsComplete = useCallback(async () => {
    if (!id || completingRef.current) return;
    completingRef.current = true;
    setFinalizing(true);

    const slowTimer = setTimeout(() => setFinalizingSlow(true), 6000);

    let attempt = 0;
    while (true) {
      attempt += 1;
      try {
        const detail = await api.getInvestigation(id);
        setInv(detail);
        if (["COMPLETED", "FAILED", "PARTIAL"].includes(detail.state)) {
          if (detail.state === "COMPLETED") fetchSecondaryData(id);
          break;
        }
      } catch {
        // keep retrying
      }
      await sleep(Math.min(1000 + attempt * 300, 4000));
    }

    clearTimeout(slowTimer);
    setFinalizing(false);
    setFinalizingSlow(false);
  }, [id, fetchSecondaryData]);

  if (notFound) {
    return (
      <div className="p-8 max-w-3xl mx-auto">
        <EmptyState
          icon={ShieldAlert}
          title="Investigation not found"
          subtitle="This investigation may have been removed, or the link is incorrect."
        />
      </div>
    );
  }

  if (!inv || !id) {
    return (
      <div className="p-5 sm:p-8 max-w-6xl mx-auto space-y-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-72" />
      </div>
    );
  }

  const rawInProgress = !["COMPLETED", "FAILED", "PARTIAL"].includes(inv.state);
  const showPipeline = rawInProgress && !finalizing;
  const showFinalizing = finalizing && inv.state !== "COMPLETED" && inv.state !== "FAILED";
  const showResult = inv.state === "COMPLETED" || (finalizing === false && inv.state === "PARTIAL");

  return (
    <div className="p-5 sm:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-6">
        <div className="min-w-0">
          <div className="text-xs text-forensic-muted mono mb-1.5 truncate">INVESTIGATION {id}</div>
          <h1 className="text-xl font-bold text-forensic-text truncate">{inv.original_filename}</h1>
          {inv.demo_mode && <div className="mt-2"><DemoTag /></div>}
        </div>
        {inv.state === "COMPLETED" && <VerdictBadge verdict={inv.verdict} size="lg" />}
      </div>

      {showPipeline && <StatusPipeline investigationId={id} onComplete={handleWsComplete} />}

      {showFinalizing && (
        <div className="panel p-8 text-center animate-fadeIn">
          <div className="w-10 h-10 mx-auto mb-4 rounded-full border-2 border-forensic-accent/30 border-t-forensic-accent ring-spin" />
          <div className="text-sm font-semibold text-forensic-text mb-1">Finalizing evidence…</div>
          <div className="text-xs text-forensic-muted max-w-sm mx-auto">
            The pipeline has finished. Confirming the final investigation record{finalizingSlow ? " — this is taking a little longer than usual, still working…" : "."}
          </div>
        </div>
      )}

      {inv.state === "FAILED" && !finalizing && (
        <div className="panel p-6 border-forensic-danger/30">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-forensic-danger/10 border border-forensic-danger/30 flex items-center justify-center text-forensic-danger flex-shrink-0">
              <AlertTriangle size={18} />
            </div>
            <div>
              <div className="text-sm font-semibold text-forensic-text mb-1">Investigation Interrupted</div>
              <div className="text-xs text-forensic-muted mb-3">What happened: {inv.error_message || "An unknown error occurred during processing."}</div>
              <button
                onClick={() => api.getInvestigation(id).then(setInv)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-forensic-border text-forensic-text2 text-xs font-medium hover:border-forensic-accent/40 hover:text-forensic-text transition"
              >
                <RefreshCw size={12} /> Refresh Status
              </button>
            </div>
          </div>
        </div>
      )}

      {showResult && (
        <>
          <div className="flex gap-1 border-b border-forensic-border mb-6 overflow-x-auto">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`flex items-center gap-1.5 px-3.5 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors focus-ring ${
                    tab === t.key ? "border-forensic-accent text-forensic-accent" : "border-transparent text-forensic-muted hover:text-forensic-text"
                  }`}
                >
                  <Icon size={14} /> {t.key}
                </button>
              );
            })}
          </div>

          <div className="animate-fadeIn">
            {tab === "Overview" && <OverviewTab inv={inv} sourcesReady report={report} />}
            {tab === "AI Detection" && <AIDetectionTab inv={inv} />}
            {tab === "Forensics" && <ForensicsTab inv={inv} investigationId={id} />}
            {tab === "Evidence" && <EvidenceTab inv={inv} investigationId={id} />}
            {tab === "Sources" && <SourcesTab inv={inv} />}
            {tab === "Timeline" && (
              <Card title="Evidence Timeline">
                {timeline.status === "loading" ? <Skeleton className="h-40" /> : <Timeline items={timeline.data || []} />}
              </Card>
            )}
            {tab === "Propagation" && (
              <Card title="Propagation Graph">
                {graph.status === "loading" ? (
                  <Skeleton className="h-96" />
                ) : graph.data ? (
                  <PropagationGraph nodes={graph.data.nodes} edges={graph.data.edges} />
                ) : (
                  <EmptyState icon={GitBranch} title="Propagation data unavailable" />
                )}
              </Card>
            )}
            {tab === "Report" && (
              report.status === "loading" ? <Skeleton className="h-96" /> :
              report.data ? <ReportTab report={report.data} /> :
              <EmptyState icon={FileText} title="Report is being prepared" subtitle="The full report will appear here once ready." />
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */

function OverviewTab({ inv, report }: { inv: InvestigationDetail; sourcesReady?: boolean; report: AsyncState<Report> }) {
  const detection = inv.ai_detection;
  const forensics = inv.forensic_results;
  const bestSource = inv.sources.slice().sort((a, b) => (b.source_confidence || 0) - (a.source_confidence || 0))[0];

  return (
    <div className="space-y-4">
      {/* Verdict hero */}
      <Card className="p-6 sm:p-8">
        <div className="grid md:grid-cols-3 gap-6 items-center">
          <div className="md:col-span-2">
            <div className="text-xs uppercase tracking-wider text-forensic-muted mb-2">Investigation Complete — Verdict</div>
            <VerdictBadge verdict={inv.verdict} size="lg" />
            <p className="text-sm text-forensic-text2 mt-4 max-w-lg">
              Overall confidence: <ConfidencePill label={inv.confidence_label} />{" "}
              {inv.overall_score != null && <span className="mono text-forensic-text">({Math.round(inv.overall_score * 100)}%)</span>}
            </p>
          </div>
          <div className="flex justify-center md:justify-end">
            <ConfidenceGauge value={inv.overall_score} label="Overall Confidence" />
          </div>
        </div>
      </Card>

      {/* Confidence breakdown */}
      <Card title="Why This Verdict — Confidence Breakdown">
        <div className="grid sm:grid-cols-3 gap-5">
          <ScoreBar label="AI Detection" value={detection?.probability ?? null} colorClass="bg-forensic-danger" />
          <ScoreBar label="Forensic Evidence" value={forensics?.forensic_score ?? null} colorClass="bg-forensic-warn" />
          <ScoreBar label="Origin Evidence" value={bestSource?.source_confidence ?? null} colorClass="bg-forensic-accent" />
        </div>
      </Card>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Key AI signals */}
        <Card title="AI Detection Summary">
          {detection ? (
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-forensic-text2">{detection.classification}</span>
                <span className="mono text-sm font-semibold text-forensic-text">{Math.round(detection.probability * 100)}%</span>
              </div>
              <ul className="space-y-1.5">
                {(detection.signals || []).slice(0, 4).map((s, i) => (
                  <li key={i} className="text-xs text-forensic-text2 flex gap-2"><span className="text-forensic-accent">›</span>{s}</li>
                ))}
              </ul>
              {detection.is_demo && <div className="mt-3"><DemoTag /></div>}
            </div>
          ) : <div className="text-sm text-forensic-muted">No detection data.</div>}
        </Card>

        {/* Earliest source */}
        <Card title="Earliest Credible Source">
          {bestSource ? (
            <div>
              <div className="text-sm font-medium text-forensic-text truncate">{bestSource.title || bestSource.domain || bestSource.platform || "Unknown source"}</div>
              <a href={bestSource.url} target="_blank" rel="noreferrer" className="text-xs text-forensic-accent break-all hover:underline inline-flex items-center gap-1 mt-1">
                Open Source <ExternalLink size={11} />
              </a>
              <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
                <div><span className="text-forensic-muted">Date</span><div className="mono text-forensic-text2">{bestSource.publication_date || "unknown"}</div></div>
                <div><span className="text-forensic-muted">Confidence</span><div className="mono text-forensic-text2">{bestSource.source_confidence != null ? `${Math.round(bestSource.source_confidence * 100)}%` : "N/A"}</div></div>
              </div>
              <div className="flex items-start gap-1.5 text-[11px] text-forensic-muted italic mt-3">
                <Info size={12} className="flex-shrink-0 mt-0.5" />
                Highest-confidence earliest occurrence found — not a guaranteed original.
              </div>
            </div>
          ) : <div className="text-sm text-forensic-muted">No sources discovered.</div>}
        </Card>
      </div>

      {/* Full report status */}
      {report.status === "loading" && (
        <Card title="Full Report"><div className="text-xs text-forensic-muted">Correlating evidence…</div></Card>
      )}

      <Card className="border-forensic-accent/20">
        <p className="text-sm text-forensic-text2">
          <span className="font-semibold text-forensic-text">Human verification recommended.</span> This platform provides
          evidence-based investigative assistance; final attribution and authentication should be confirmed by a qualified
          digital-forensics expert before any legal, journalistic, or moderation action.
        </p>
      </Card>
    </div>
  );
}

function AIDetectionTab({ inv }: { inv: InvestigationDetail }) {
  const d = inv.ai_detection;
  if (!d) return <Card><EmptyState icon={Bot} title="No detection data available" /></Card>;
  return (
    <Card title="AI / Manipulation Detection">
      {d.is_demo && (
        <div className="mb-4 p-3 rounded-lg bg-forensic-warn/10 border border-forensic-warn/30 text-forensic-warn text-xs">
          DEMO / HEURISTIC ANALYSIS — this used the platform's transparent demo detector, combining forensic signals, not a
          validated deepfake-detection model.
        </div>
      )}
      <div className="grid md:grid-cols-2 gap-6">
        <div>
          <ConfidenceGauge value={d.probability} label={d.classification} />
        </div>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between border-b border-forensic-border/40 pb-2"><span className="text-forensic-muted">Classification</span><span className="mono font-semibold">{d.classification}</span></div>
          <div className="flex justify-between border-b border-forensic-border/40 pb-2"><span className="text-forensic-muted">Confidence</span><ConfidencePill label={d.confidence.toUpperCase()} /></div>
          <div className="flex justify-between border-b border-forensic-border/40 pb-2"><span className="text-forensic-muted">Model</span><span className="mono">{d.model_name}</span></div>
        </div>
      </div>
      <div className="mt-6">
        <div className="text-xs uppercase tracking-wider text-forensic-muted mb-2.5">Detection Signals</div>
        <div className="grid sm:grid-cols-2 gap-2">
          {(d.signals || []).map((s, i) => (
            <div key={i} className="flex gap-2.5 p-3 rounded-lg border border-forensic-border bg-forensic-panel3/50 text-sm text-forensic-text2">
              <span className="text-forensic-accent flex-shrink-0">●</span>{s}
            </div>
          ))}
          {(!d.signals || d.signals.length === 0) && <div className="text-sm text-forensic-muted">No individual signals reported.</div>}
        </div>
      </div>
    </Card>
  );
}

function ForensicsTab({ inv, investigationId }: { inv: InvestigationDetail; investigationId: string }) {
  const f = inv.forensic_results;
  if (!f) return <Card><EmptyState icon={Microscope} title="No forensic data available" /></Card>;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card title="Error Level Analysis (ELA)">
        {inv.media_type === "image" ? (
          <img src={api.elaUrl(investigationId)} alt="ELA visualization" className="rounded-lg border border-forensic-border w-full" />
        ) : (
          <div className="text-sm text-forensic-muted">Frame-level ELA computed per sampled frame; see Evidence tab.</div>
        )}
        <div className="mt-3 text-xs text-forensic-warn bg-forensic-warn/10 border border-forensic-warn/30 rounded-lg p-2.5">
          ELA is an investigative indicator and is not conclusive proof of manipulation.
        </div>
        <div className="mt-2 text-xs text-forensic-muted mono">Score: {f.ela_score ?? "N/A"}</div>
      </Card>
      <Card title="Noise & Resampling">
        <div className="space-y-4">
          <ScoreBar label="Noise Consistency Anomaly" value={f.noise_score} colorClass="bg-forensic-warn" />
          <ScoreBar label="Resampling Artifact Score" value={f.resampling_score} colorClass="bg-forensic-warn" />
        </div>
      </Card>
      <Card title="Compression Notes" className="md:col-span-2">
        <pre className="text-xs mono text-forensic-muted overflow-x-auto whitespace-pre-wrap bg-forensic-panel3/40 p-3 rounded-lg border border-forensic-border/60">
          {JSON.stringify(f.compression_notes, null, 2)}
        </pre>
      </Card>
      {f.suspicious_indicators && f.suspicious_indicators.length > 0 && (
        <Card title="Suspicious Indicators" className="md:col-span-2">
          <div className="grid sm:grid-cols-2 gap-2">
            {f.suspicious_indicators.map((s, i) => (
              <div key={i} className="flex gap-2.5 p-3 rounded-lg border border-forensic-warn/25 bg-forensic-warn/5 text-sm text-forensic-warn">
                <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" />{s}
              </div>
            ))}
          </div>
        </Card>
      )}
      {f.frame_analysis && (
        <Card title="Frame Analysis" className="md:col-span-2">
          <div className="text-sm text-forensic-muted">
            {f.frame_analysis.frames_analyzed} frame(s) analyzed. Suspicious frames: {(f.frame_analysis.suspicious_frames || []).join(", ") || "none"}
          </div>
        </Card>
      )}
    </div>
  );
}

function EvidenceTab({ inv, investigationId }: { inv: InvestigationDetail; investigationId: string }) {
  const asset = inv.media_asset;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card title="Original Evidence">
        {inv.media_type === "image" ? (
          <img src={api.originalUrl(investigationId)} alt="original evidence" className="rounded-lg border border-forensic-border w-full" />
        ) : (
          <video src={api.originalUrl(investigationId)} controls className="rounded-lg border border-forensic-border w-full" />
        )}
        <div className="grid grid-cols-2 gap-3 mt-3 text-xs">
          <div><span className="text-forensic-muted">Size</span><div className="mono text-forensic-text2">{asset?.size_bytes ? `${(asset.size_bytes / 1024).toFixed(1)} KB` : "—"}</div></div>
          <div><span className="text-forensic-muted">Type</span><div className="mono text-forensic-text2">{asset?.mime_type || "—"}</div></div>
          {asset?.width && <div><span className="text-forensic-muted">Dimensions</span><div className="mono text-forensic-text2">{asset.width}×{asset.height}</div></div>}
          <div><span className="text-forensic-muted">GPS metadata</span><div className="mono text-forensic-text2">{asset?.gps_present ? "Present" : "Not present"}</div></div>
        </div>
      </Card>
      <Card title="Integrity & Perceptual Hashes">
        <div>
          <HashDisplay label="SHA-256" value={asset?.sha256} />
          <HashDisplay label="pHash" value={asset?.phash} />
          <HashDisplay label="dHash" value={asset?.dhash} />
          <HashDisplay label="aHash" value={asset?.ahash} />
        </div>
        <details className="mt-4 group">
          <summary className="text-xs uppercase tracking-wider text-forensic-muted cursor-pointer select-none hover:text-forensic-text2 transition-colors">
            Raw Metadata ▸
          </summary>
          <pre className="text-[11px] mono text-forensic-muted overflow-x-auto max-h-64 whitespace-pre-wrap mt-2 bg-forensic-panel3/40 p-3 rounded-lg border border-forensic-border/60">
            {JSON.stringify(asset?.metadata_json, null, 2)}
          </pre>
        </details>
      </Card>
      <Card title="Chain of Custody / Event Log" className="md:col-span-2">
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {inv.events.map((e, i) => (
            <div key={i} className="text-xs mono flex gap-3 py-1.5 border-b border-forensic-border/30 last:border-0">
              <span className="text-forensic-muted flex-shrink-0">{new Date(e.timestamp).toLocaleTimeString()}</span>
              <span className="text-forensic-accent flex-shrink-0">[{e.agent}]</span>
              <span className="text-forensic-text2">{e.action}</span>
            </div>
          ))}
          {inv.events.length === 0 && <div className="text-sm text-forensic-muted py-4 text-center">No events recorded.</div>}
        </div>
      </Card>
    </div>
  );
}

function SourceCard({ s, rank }: { s: SourceItem; rank: number }) {
  return (
    <div className="panel panel-hover p-4">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="text-sm font-medium text-forensic-text flex items-center gap-2 min-w-0">
          <span className="mono text-xs text-forensic-muted flex-shrink-0">#{rank}</span>
          <span className="truncate">{s.title || s.platform || s.domain || "Unknown source"}</span>
          {s.is_demo && <DemoTag />}
        </div>
        <span className="mono text-xs text-forensic-muted flex-shrink-0">{s.classification}</span>
      </div>
      <a href={s.url} target="_blank" rel="noreferrer" className="text-xs text-forensic-muted break-all hover:text-forensic-accent transition-colors inline-flex items-center gap-1">
        {s.url} <ExternalLink size={10} />
      </a>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs">
        <span className="text-forensic-muted">Date: <span className="mono text-forensic-text2">{s.publication_date || "unknown"}</span></span>
        <span className="text-forensic-muted">Similarity: <span className="mono text-forensic-text2">{s.similarity_score != null ? `${Math.round(s.similarity_score * 100)}%` : "N/A"}</span></span>
        <span className="text-forensic-muted">Confidence: <span className="mono text-forensic-text2">{s.source_confidence != null ? `${Math.round(s.source_confidence * 100)}%` : "N/A"}</span></span>
        <span className="text-forensic-muted">Match: <span className="mono text-forensic-text2">{s.match_category || "—"}</span></span>
      </div>
      {!s.accessible && (
        <div className="text-xs text-forensic-danger mt-2 flex items-center gap-1.5"><AlertTriangle size={12} /> Source inaccessible — manual verification required. {s.inaccessible_reason}</div>
      )}
      {s.reasoning && s.reasoning.length > 0 && (
        <ul className="mt-2.5 space-y-0.5 border-t border-forensic-border/40 pt-2.5">
          {s.reasoning.map((r, ri) => <li key={ri} className="text-[11px] text-forensic-muted">• {r}</li>)}
        </ul>
      )}
    </div>
  );
}

function SourcesTab({ inv }: { inv: InvestigationDetail }) {
  const sorted = inv.sources.slice().sort((a, b) => (b.source_confidence || 0) - (a.source_confidence || 0));
  const best = sorted[0];
  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs uppercase tracking-wider text-forensic-muted mb-1">Source Trace</div>
        <p className="text-sm text-forensic-muted mb-4">Potential web origins and occurrences discovered for this media.</p>
      </div>

      {best && (
        <Card title="Earliest Credible Occurrence" className="border-forensic-accent/25">
          <div className="grid sm:grid-cols-4 gap-4 text-sm mb-3">
            <div><div className="text-forensic-muted text-xs mb-0.5">Date</div><div className="mono">{best.publication_date || "unknown"}</div></div>
            <div><div className="text-forensic-muted text-xs mb-0.5">Platform</div><div>{best.platform || best.domain || "—"}</div></div>
            <div><div className="text-forensic-muted text-xs mb-0.5">Similarity</div><div className="mono">{best.similarity_score != null ? `${Math.round(best.similarity_score * 100)}%` : "N/A"}</div></div>
            <div><div className="text-forensic-muted text-xs mb-0.5">Confidence</div><div className="mono">{best.source_confidence != null ? `${Math.round(best.source_confidence * 100)}%` : "N/A"}</div></div>
          </div>
          <a href={best.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-forensic-accent/40 text-forensic-accent text-xs font-medium hover:bg-forensic-accent/10 transition">
            Open Source <ExternalLink size={12} />
          </a>
          <div className="flex items-start gap-1.5 text-[11px] text-forensic-muted italic mt-3">
            <Info size={12} className="flex-shrink-0 mt-0.5" />
            This is the highest-confidence earliest occurrence found during this investigation, not a confirmed original.
          </div>
        </Card>
      )}

      <div>
        <div className="text-xs uppercase tracking-wider text-forensic-muted mb-3">Other Occurrences ({sorted.length})</div>
        {sorted.length === 0 ? (
          <Card><EmptyState icon={Globe2} title="No sources discovered" subtitle="The origin-search pipeline did not surface any web occurrences for this media." /></Card>
        ) : (
          <div className="space-y-3">
            {sorted.map((s, i) => <SourceCard key={s.id} s={s} rank={i + 1} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function ReportTab({ report }: { report: Report }) {
  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <Card title={title} className="mb-4">{children}</Card>
  );
  return (
    <div>
      <Section title="Executive Summary">
        <div className="flex flex-wrap items-center gap-4">
          <VerdictBadge verdict={report.executive_summary.verdict} />
          <span className="text-sm text-forensic-text2">Confidence: <ConfidencePill label={report.executive_summary.confidence} /></span>
        </div>
      </Section>
      <Section title="What We Know">
        <ul className="space-y-1.5">{report.what_we_know.map((x, i) => <li key={i} className="text-sm text-forensic-text2 flex gap-2"><span className="text-forensic-success">✓</span>{x}</li>)}</ul>
      </Section>
      <Section title="What We Suspect">
        <ul className="space-y-1.5">{report.what_we_suspect.map((x, i) => <li key={i} className="text-sm text-forensic-warn flex gap-2"><span>~</span>{x}</li>)}</ul>
      </Section>
      <Section title="What We Could Not Verify">
        <ul className="space-y-1.5">{report.what_we_could_not_verify.map((x, i) => <li key={i} className="text-sm text-forensic-muted flex gap-2"><span>?</span>{x}</li>)}</ul>
      </Section>
      <Section title="Limitations">
        <ul className="space-y-1.5">{report.limitations.map((x, i) => <li key={i} className="text-sm text-forensic-muted flex gap-2"><span>•</span>{x}</li>)}</ul>
      </Section>
      <Section title="Recommended Human Verification">
        <p className="text-sm text-forensic-text2">{report.recommended_human_verification}</p>
      </Section>
    </div>
  );
}
