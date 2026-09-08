import type { Investigation, InvestigationDetail, Report, GraphNode, GraphEdge, SourceItem } from "../types";

const BASE = "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try { const body = await res.json(); detail = body.detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => fetch(`${BASE}/health`).then((r) => j<{ status: string; demo_mode: boolean; openclaw_enabled: boolean }>(r)),
  stats: () => fetch(`${BASE}/stats`).then((r) => j<any>(r)),

  listInvestigations: () => fetch(`${BASE}/investigations`).then((r) => j<Investigation[]>(r)),
  getInvestigation: (id: string) => fetch(`${BASE}/investigations/${id}`).then((r) => j<InvestigationDetail>(r)),
  getStatus: (id: string) => fetch(`${BASE}/investigations/${id}/status`).then((r) => j<{ state: string; error_message: string | null; events: any[] }>(r)),
  getReport: (id: string) => fetch(`${BASE}/investigations/${id}/report`).then((r) => j<Report>(r)),
  getSources: (id: string) => fetch(`${BASE}/investigations/${id}/sources`).then((r) => j<SourceItem[]>(r)),
  getGraph: (id: string) => fetch(`${BASE}/investigations/${id}/graph`).then((r) => j<{ nodes: GraphNode[]; edges: GraphEdge[] }>(r)),
  getTimeline: (id: string) => fetch(`${BASE}/investigations/${id}/timeline`).then((r) => j<any[]>(r)),

  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/investigations`, { method: "POST", body: form }).then((r) => j<Investigation>(r));
  },
  start: (id: string) => fetch(`${BASE}/investigations/${id}/start`, { method: "POST" }).then((r) => j<Investigation>(r)),
  seedDemo: () => fetch(`${BASE}/demo/seed`, { method: "POST" }).then((r) => j<Investigation>(r)),

  originalUrl: (id: string) => `${BASE}/investigations/${id}/original`,
  elaUrl: (id: string) => `${BASE}/investigations/${id}/artifacts/ela`,

  connectWs: (id: string, onMessage: (data: any) => void, onClose?: () => void) => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/api/investigations/ws/${id}`);
    ws.onmessage = (ev) => onMessage(JSON.parse(ev.data));
    ws.onclose = () => onClose?.();
    return ws;
  },
};
