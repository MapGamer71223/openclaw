/**
 * Investigation service -- talks to the real JanSatark AI backend
 * (FastAPI, see app/api/investigations.py and app/api/demo.py).
 *
 * All backend-shape knowledge (field names, enums) lives in
 * types/investigation.ts's map* helpers; this file only deals in the
 * clean frontend types.
 */
import { apiAssetUrl, apiGet, apiPost, apiUpload, UploadFileInput } from '@/services/api';
import {
  BackendAIDetection,
  BackendForensicResult,
  BackendGraphResponse,
  BackendInvestigation,
  BackendInvestigationDetail,
  BackendSource,
  BackendStats,
  BackendStatusResponse,
  Investigation,
  InsightsSummary,
  mapAIDetection,
  mapForensics,
  mapInsights,
  mapInvestigation,
  mapMetadata,
  mapPropagationGraph,
  mapSource,
  mapTimelineEntry,
  AIDetectionDetails,
  ForensicDetails,
  MetadataDetails,
  PropagationGraph,
  SourceMatch,
  TimelineEntry,
} from '@/types/investigation';

export type InvestigationMode = 'quick' | 'deep';

export function originalMediaUrl(id: string): string {
  return apiAssetUrl(`/api/investigations/${id}/original`);
}

/** GET /api/investigations -- investigation history list. */
export async function getInvestigations(): Promise<Investigation[]> {
  const list = await apiGet<BackendInvestigation[]>('/api/investigations');
  return list.map((inv) => mapInvestigation(inv, originalMediaUrl(inv.id)));
}

/** GET /api/investigations/{id} -- full detail, mapped to the frontend summary shape. */
export async function getInvestigationById(id: string): Promise<Investigation> {
  const detail = await apiGet<BackendInvestigationDetail>(`/api/investigations/${id}`);
  return mapInvestigation(detail, originalMediaUrl(detail.id));
}

/** GET /api/investigations/{id} -- raw detail payload, for screens that need everything at once. */
export async function getInvestigationDetail(id: string): Promise<BackendInvestigationDetail> {
  return apiGet<BackendInvestigationDetail>(`/api/investigations/${id}`);
}

/**
 * POST /api/investigations -- uploads media (multipart/form-data) and
 * creates a new investigation in the UPLOADED state. Does not start
 * analysis -- call startInvestigation() next.
 */
export async function createInvestigation(file: UploadFileInput): Promise<Investigation> {
  const created = await apiUpload<BackendInvestigation>('/api/investigations', file, 'file');
  return mapInvestigation(created, originalMediaUrl(created.id));
}

/**
 * POST /api/investigations/{id}/start (deep) or /start-fast (quick).
 * Kicks off background analysis; the investigation moves out of
 * UPLOADED and progresses through the pipeline stages. Poll
 * getInvestigationStatus() afterwards to track it.
 */
export async function startInvestigation(id: string, mode: InvestigationMode = 'deep'): Promise<Investigation> {
  const path = mode === 'quick' ? `/api/investigations/${id}/start-fast` : `/api/investigations/${id}/start`;
  const started = await apiPost<BackendInvestigation>(path);
  return mapInvestigation(started, originalMediaUrl(started.id));
}

/** GET /api/investigations/{id}/status -- lightweight polling target: state + full event log. */
export async function getInvestigationStatus(id: string): Promise<BackendStatusResponse> {
  return apiGet<BackendStatusResponse>(`/api/investigations/${id}/status`);
}

/** GET /api/investigations/{id}/detections */
export async function getAIDetection(id: string): Promise<AIDetectionDetails | null> {
  try {
    const detection = await apiGet<BackendAIDetection>(`/api/investigations/${id}/detections`);
    return mapAIDetection(detection);
  } catch (err: any) {
    if (err?.status === 404) return null;
    throw err;
  }
}

/** GET /api/investigations/{id}/forensics */
export async function getForensics(id: string): Promise<ForensicDetails | null> {
  try {
    const forensics = await apiGet<BackendForensicResult>(`/api/investigations/${id}/forensics`);
    return mapForensics(forensics);
  } catch (err: any) {
    if (err?.status === 404) return null;
    throw err;
  }
}

/** Metadata comes back nested inside the investigation detail's media_asset. */
export async function getMetadata(id: string): Promise<MetadataDetails | null> {
  const detail = await getInvestigationDetail(id);
  return detail.media_asset ? mapMetadata(detail.media_asset) : null;
}

/** GET /api/investigations/{id}/sources */
export async function getSources(id: string): Promise<SourceMatch[]> {
  const sources = await apiGet<BackendSource[]>(`/api/investigations/${id}/sources`);
  return sources.map(mapSource);
}

/** GET /api/investigations/{id}/timeline -- prefer the richer /status events for a full agent-by-agent feed. */
export async function getTimeline(id: string): Promise<TimelineEntry[]> {
  const status = await getInvestigationStatus(id);
  return status.events.map(mapTimelineEntry);
}

/** GET /api/investigations/{id}/graph -- propagation nodes/edges. */
export async function getPropagationGraph(id: string): Promise<PropagationGraph> {
  const graph = await apiGet<BackendGraphResponse>(`/api/investigations/${id}/graph`);
  return mapPropagationGraph(graph);
}

/** GET /api/stats -- lightweight aggregate counts used by the Insights tab. */
export async function getStats(): Promise<BackendStats> {
  return apiGet<BackendStats>('/api/stats');
}

export async function getInsights(investigations: Investigation[]): Promise<InsightsSummary> {
  const stats = await getStats();
  return mapInsights(stats, investigations);
}

/** GET /api/health -- used to show a "backend unreachable" banner instead of failing silently. */
export async function getHealth(): Promise<{ status: string; demo_mode: boolean; ai_detector_status: string }> {
  return apiGet('/api/health');
}

/**
 * POST /api/demo/seed -- generates a synthetic sample image and runs it
 * through the ENTIRE real pipeline synchronously (hashing, AI
 * detection, forensics, OSINT, propagation, report). Used by the "Use a
 * demo image" action on the New Investigation screen when the person
 * doesn't want to upload their own file. Only the OSINT/source layer is
 * demo data (each source comes back with is_demo: true); everything
 * else is the real pipeline.
 */
export async function seedDemoInvestigation(): Promise<Investigation> {
  const created = await apiPost<BackendInvestigation>('/api/demo/seed');
  return mapInvestigation(created, originalMediaUrl(created.id));
}
