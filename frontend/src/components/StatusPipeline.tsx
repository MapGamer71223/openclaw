import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Fingerprint, FileSearch, Bot, Microscope, Globe, BadgeCheck,
  GitBranch, Layers, FileText, CheckCircle2, Loader2, Circle, Terminal,
} from "lucide-react";
import { api } from "../services/api";

const STAGES: { key: string; label: string; desc: string; icon: React.ElementType }[] = [
  { key: "HASHING", label: "Hashing", desc: "Generating cryptographic fingerprints", icon: Fingerprint },
  { key: "METADATA_ANALYSIS", label: "Metadata Analysis", desc: "Extracting embedded file metadata", icon: FileSearch },
  { key: "AI_ANALYSIS", label: "AI Detection", desc: "Analyzing generative-model signals", icon: Bot },
  { key: "FORENSIC_ANALYSIS", label: "Forensic Analysis", desc: "ELA, noise & resampling analysis", icon: Microscope },
  { key: "ORIGIN_SEARCH", label: "Origin Search", desc: "Searching the web for occurrences", icon: Globe },
  { key: "SOURCE_VERIFICATION", label: "Source Verification", desc: "Verifying candidate sources", icon: BadgeCheck },
  { key: "PROPAGATION_ANALYSIS", label: "Propagation Analysis", desc: "Mapping how media spread online", icon: GitBranch },
  { key: "CORRELATION", label: "Evidence Correlation", desc: "Correlating findings across signals", icon: Layers },
  { key: "REPORT_GENERATION", label: "Report Generation", desc: "Compiling the investigation report", icon: FileText },
  { key: "COMPLETED", label: "Complete", desc: "Investigation finished", icon: CheckCircle2 },
];

export function StatusPipeline({ investigationId, onComplete }: { investigationId: string; onComplete?: () => void }) {
  const [events, setEvents] = useState<any[]>([]);
  const [state, setState] = useState<string>("UPLOADED");
  const doneRef = useRef(false);

  const fireOnce = () => {
    if (doneRef.current) return;
    doneRef.current = true;
    onComplete?.();
  };

  useEffect(() => {
    let cancelled = false;
    doneRef.current = false;

    const checkStatus = () => {
      if (cancelled) return;
      api.getStatus(investigationId).then((s) => {
        if (cancelled) return;
        setState(s.state);
        if (s.state === "COMPLETED" || s.state === "FAILED" || s.state === "PARTIAL") fireOnce();
      }).catch(() => {});
    };

    const ws = api.connectWs(
      investigationId,
      (msg) => {
        if (cancelled) return;
        if (msg.stage) setEvents((prev) => [...prev, msg]);
        if (msg.state) setState(msg.state);
      },
      () => checkStatus()
    );

    // Belt-and-braces poll in case the socket stays open or closes without
    // the backend state having fully settled yet (avoids getting stuck).
    const poll = setInterval(checkStatus, 3000);

    return () => { cancelled = true; ws.close(); clearInterval(poll); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId]);

  const reachedStages = useMemo(() => new Set(events.map((e) => e.stage)), [events]);
  const currentIndex = Math.max(0, ...STAGES.map((s, i) => (reachedStages.has(s.key) ? i : -1)));
  const isTerminal = state === "COMPLETED" || state === "FAILED" || state === "PARTIAL";
  const overallPct = Math.round(((currentIndex + 1) / STAGES.length) * 100);

  return (
    <div className="panel p-5 sm:p-6 animate-fadeIn">
      <div className="flex items-center justify-between mb-1.5">
        <h3 className="text-sm font-semibold text-forensic-text">Investigation In Progress</h3>
        <span className="mono text-xs text-forensic-accent font-medium">{state}</span>
      </div>
      <div className="flex items-center gap-3 mb-6">
        <div className="flex-1 h-2 bg-forensic-panel3 rounded-full overflow-hidden border border-forensic-border">
          <div
            className="h-full bg-gradient-to-r from-forensic-accent to-forensic-violet rounded-full transition-all duration-700 ease-out"
            style={{ width: `${isTerminal ? 100 : overallPct}%` }}
          />
        </div>
        <span className="mono text-xs text-forensic-muted flex-shrink-0">{isTerminal ? 100 : overallPct}%</span>
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 space-y-0.5">
          {STAGES.map((s, i) => {
            const done = i <= currentIndex;
            const active = i === currentIndex + 1 && !isTerminal;
            const Icon = s.icon;
            return (
              <div
                key={s.key}
                className={`flex items-center gap-3 py-2.5 px-3 rounded-lg transition-colors ${
                  active ? "bg-forensic-accent/5 border border-forensic-accent/20" : "border border-transparent"
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${
                    done
                      ? "bg-forensic-success/10 border-forensic-success/30 text-forensic-success"
                      : active
                      ? "bg-forensic-accent/10 border-forensic-accent/40 text-forensic-accent shadow-glow"
                      : "bg-forensic-panel3 border-forensic-border text-forensic-faint"
                  }`}
                >
                  {done ? <CheckCircle2 size={15} /> : active ? <Loader2 size={15} className="animate-spin" /> : <Icon size={14} />}
                </div>
                <div className="min-w-0">
                  <div className={`text-sm font-medium truncate ${done || active ? "text-forensic-text" : "text-forensic-muted"}`}>
                    {String(i + 1).padStart(2, "0")}. {s.label}
                  </div>
                  <div className="text-[11px] text-forensic-muted truncate">{s.desc}</div>
                </div>
                {active && <span className="ml-auto w-2 h-2 rounded-full bg-forensic-accent pulse-dot flex-shrink-0" />}
              </div>
            );
          })}
        </div>

        <div className="lg:col-span-2">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-forensic-muted mb-2">
            <Terminal size={12} /> Live Investigation Log
          </div>
          <div className="rounded-lg border border-forensic-border bg-forensic-panel3/60 p-3 h-64 lg:h-full overflow-y-auto space-y-1.5">
            {events.length === 0 && (
              <div className="text-[11px] text-forensic-muted italic flex items-center gap-1.5 py-2">
                <Circle size={8} className="animate-pulse" /> Waiting for engine events…
              </div>
            )}
            {events.slice(-40).map((e, idx) => (
              <div key={idx} className="text-[11px] mono leading-relaxed animate-fadeIn">
                <div className="text-forensic-faint">
                  [{e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : "--:--:--"}]{" "}
                  <span className="text-forensic-accent">{e.agent || e.stage}</span>
                </div>
                <div className="text-forensic-text2">{e.action}{e.detail ? ` — ${e.detail}` : ""}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
