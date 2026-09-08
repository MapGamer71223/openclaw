import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../services/api";
import type { InvestigationDetail } from "../types";
import { VerdictBadge, Card } from "../components/ui";
import { FastStatusPipeline } from "../components/FastStatusPipeline";

export function FastResultPage() {
  const { id } = useParams<{ id: string }>();
  const [inv, setInv] = useState<InvestigationDetail | null>(null);

  const load = async () => {
    if (!id) return;
    const detail = await api.getInvestigation(id);
    setInv(detail);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!inv || !id) return <div className="p-8 text-forensic-muted">Loading…</div>;

  const inProgress = !["COMPLETED", "FAILED", "PARTIAL"].includes(inv.state);
  const isAI = inv.verdict === "AI_GENERATED" || inv.verdict === "AI_ALTERED";
  const sorted = inv.sources.slice().sort((a, b) => (b.source_confidence || 0) - (a.source_confidence || 0));
  const earliest = sorted[0];

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <Link to="/upload" className="text-xs text-forensic-muted hover:text-forensic-text mb-4 inline-block">
        ← Check another file
      </Link>

      <div className="mb-6">
        <img src={api.originalUrl(id)} alt="" className="w-full max-h-96 object-contain rounded-lg border border-forensic-border" />
      </div>

      {inProgress ? (
        <FastStatusPipeline investigationId={id} onComplete={load} />
      ) : inv.state === "FAILED" ? (
        <div className="panel p-6 border-forensic-danger/40 text-forensic-danger text-sm">
          Something went wrong: {inv.error_message}
        </div>
      ) : (
        <div className="space-y-4">
          <Card>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-wider text-forensic-muted mb-2">Result</div>
                <VerdictBadge verdict={inv.verdict} />
              </div>
              {inv.ai_detection && (
                <div className="text-right">
                  <div className="text-xs text-forensic-muted">Probability</div>
                  <div className="text-2xl font-bold text-forensic-text mono">
                    {Math.round((inv.ai_detection.probability || 0) * 100)}%
                  </div>
                </div>
              )}
            </div>
            {inv.ai_detection?.is_demo && (
              <div className="mt-4 p-3 rounded-lg bg-forensic-warn/10 border border-forensic-warn/30 text-forensic-warn text-xs">
                Demo/heuristic detector — not a validated deepfake-detection model.
              </div>
            )}
          </Card>

          {isAI && (
            <Card title="Earliest Post Found">
              {earliest ? (
                <div>
                  <div className="grid grid-cols-3 gap-4 text-sm mb-3">
                    <div>
                      <div className="text-forensic-muted text-xs">Date</div>
                      <div className="mono">{earliest.publication_date || "unknown"}</div>
                    </div>
                    <div>
                      <div className="text-forensic-muted text-xs">Platform</div>
                      <div>{earliest.platform || "—"}</div>
                    </div>
                    <div>
                      <div className="text-forensic-muted text-xs">Similarity</div>
                      <div className="mono">
                        {earliest.similarity_score != null ? `${Math.round(earliest.similarity_score * 100)}%` : "N/A"}
                      </div>
                    </div>
                  </div>
                  <a
                    href={earliest.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-forensic-accent break-all hover:underline"
                  >
                    {earliest.url}
                  </a>
                  <div className="text-[11px] text-forensic-muted italic mt-3">
                    This is the earliest occurrence found during search, not a guaranteed original — please verify manually.
                  </div>
                </div>
              ) : (
                <div className="text-sm text-forensic-muted">
                  No matching posts were found online for this image.
                </div>
              )}
            </Card>
          )}

          {isAI && sorted.length > 1 && (
            <Card title={`Other Occurrences Found (${sorted.length - 1})`}>
              <div className="space-y-2">
                {sorted.slice(1).map((s) => (
                  <div key={s.id} className="text-xs flex items-center justify-between gap-3 py-1.5 border-b border-forensic-border/40">
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-forensic-muted hover:text-forensic-text break-all">
                      {s.platform || s.domain} — {s.url}
                    </a>
                    <span className="mono text-forensic-muted flex-shrink-0">{s.publication_date || "unknown"}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
