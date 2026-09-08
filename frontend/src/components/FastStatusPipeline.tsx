import React, { useEffect, useRef, useState } from "react";
import { api } from "../services/api";

type FastStage = "HASHING" | "AI_ANALYSIS" | "ORIGIN_SEARCH" | "COMPLETED";

const STAGE_COPY: Record<string, string> = {
  HASHING: "Reading file…",
  AI_ANALYSIS: "Checking if this image is AI-generated…",
  ORIGIN_SEARCH: "Searching the web for the first/original post…",
};

export function FastStatusPipeline({
  investigationId,
  onComplete,
}: {
  investigationId: string;
  onComplete?: () => void;
}) {
  const [events, setEvents] = useState<any[]>([]);
  const [state, setState] = useState<string>("UPLOADED");
  const doneRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const ws = api.connectWs(
      investigationId,
      (msg) => {
        if (cancelled) return;
        if (msg.stage || msg.action) setEvents((prev) => [...prev, msg]);
      },
      () => {
        if (cancelled) return;
        api.getStatus(investigationId).then((s) => {
          setState(s.state);
          if ((s.state === "COMPLETED" || s.state === "FAILED") && !doneRef.current) {
            doneRef.current = true;
            onComplete?.();
          }
        });
      }
    );
    return () => {
      cancelled = true;
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId]);

  const latestStage: FastStage = (events.filter((e) => e.stage).slice(-1)[0]?.stage as FastStage) || "HASHING";
  const latestAction = events.slice(-1)[0]?.action;

  return (
    <div className="panel evidence-corners p-10 text-center relative overflow-hidden">
      <div className="scan-sweep" />
      <div className="mx-auto mb-6 w-14 h-14 rounded-full border-2 border-forensic-accent/40 border-t-forensic-accent animate-spin" />
      <div className="text-lg font-semibold text-forensic-text mb-2">
        {STAGE_COPY[latestStage] || "Working…"}
      </div>
      {latestAction && (
        <div className="text-xs mono text-forensic-muted">{latestAction}</div>
      )}
      <div className="mt-6 text-[11px] mono text-forensic-muted">{state}</div>
    </div>
  );
}
