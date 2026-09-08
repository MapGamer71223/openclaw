// ---------------------------------------------------------------------
// FRONTEND-FACING TYPES
// These are the shapes the UI components already expect. Values coming
// back from the backend are normalized into these via the map* helpers
// at the bottom of this file, so screens never need to know about
// backend-specific enums (AI_GENERATED, UPLOADED, etc).
// ---------------------------------------------------------------------

export type Verdict =
  | 'AI Generated'
  | 'AI Altered'
  | 'Likely Authentic'
  | 'Inconclusive'
  | 'Analysis Unavailable';

export type MediaType = 'image' | 'video';

export type InvestigationStatus = 'processing' | 'completed' | 'failed';

export interface Investigation {
  id: string;
  filename: string;
  type: MediaType;
  thumbnail: string;
  verdict: Verdict;
  confidence: number;
  sourceCount: number;
  date: string;
  /** Raw ISO created_at, for client-side aggregation (charts, sorting). */
  createdAt: string;
  resolution: string;
  fileSize: string;
  status: InvestigationStatus;
  /** Raw backend state (e.g. "AI_ANALYSIS", "COMPLETED", "FAILED") for screens that want it. */
  rawState?: string;
  errorMessage?: string | null;
}

export interface ProgressItem {
  label: string;
  detail: string;
  status: 'completed' | 'active' | 'pending';
  stage?: string;
}

export interface SourceMatch {
  id: string;
  title: string;
  domain: string;
  date: string;
  similarity: number;
  confidence: string;
  match: 'Exact Match' | 'Near Duplicate' | 'Similar Image' | 'Possible Origin' | 'Related';
  thumbnail: string;
  url?: string;
  accessible?: boolean;
}

export interface TimelineEntry {
  title: string;
  agent: string;
  description: string;
  time: string;
  stage?: string | null;
  icon: string;
}

export interface AIDetectionDetails {
  classification: string;
  probability: number;
  confidence: string;
  modelName: string;
  signals: string[];
  isDemo: boolean;
  detectorStatus: 'demo' | 'real' | 'unavailable';
}

export interface ForensicMetric {
  label: string;
  value: string;
  pct: number;
  status: string;
}

export interface ForensicDetails {
  forensicScore: number | null;
  elaScore: number | null;
  noiseScore: number | null;
  resamplingScore: number | null;
  suspiciousIndicators: string[];
  metrics: ForensicMetric[];
}

export interface MetadataDetails {
  sha256: string | null;
  sizeBytes: number | null;
  mimeType: string | null;
  width: number | null;
  height: number | null;
  durationSeconds: number | null;
  gpsPresent: boolean;
  cameraInfo: string | null;
  editingSoftware: string | null;
  raw: Record<string, unknown> | null;
}

export interface PropagationNode {
  id: string;
  type: string;
  platform: string | null;
  url: string | null;
  timestamp: string | null;
  similarityScore: number | null;
  evidenceConfidence: number | null;
}

export interface PropagationEdge {
  from: string;
  to: string;
  type: string;
}

export interface PropagationGraph {
  nodes: PropagationNode[];
  edges: PropagationEdge[];
}

export interface InsightsSummary {
  totalInvestigations: number;
  aiGenerated: number;
  aiAltered: number;
  authentic: number;
  inconclusive: number;
  sourcesTraced: number;
  averageConfidence: number | null;
}

// ---------------------------------------------------------------------
// BACKEND-FACING TYPES
// These mirror app/schemas/investigation.py in the FastAPI backend.
// Keep in sync with that file if the backend response shape changes.
// ---------------------------------------------------------------------

export interface BackendMediaAsset {
  sha256: string;
  size_bytes: number;
  mime_type: string;
  width?: number | null;
  height?: number | null;
  duration_seconds?: number | null;
  gps_present: boolean;
  phash?: string | null;
  dhash?: string | null;
  ahash?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface BackendForensicResult {
  ela_score?: number | null;
  noise_score?: number | null;
  resampling_score?: number | null;
  compression_notes?: unknown;
  suspicious_indicators?: string[] | null;
  frame_analysis?: unknown;
  forensic_score?: number | null;
}

export interface BackendAIDetection {
  classification: string;
  probability: number;
  confidence: string;
  model_name: string;
  signals?: string[] | null;
  is_demo: boolean;
  detector_status: 'demo' | 'real' | 'unavailable';
}

export interface BackendSource {
  id: string;
  url: string;
  title?: string | null;
  platform?: string | null;
  domain?: string | null;
  publication_date?: string | null;
  date_found: string;
  similarity_score?: number | null;
  phash_distance?: number | null;
  match_category?: string | null;
  source_confidence?: number | null;
  classification?: string | null;
  reasoning?: unknown;
  accessible: boolean;
  inaccessible_reason?: string | null;
  is_demo: boolean;
  thumbnail_url?: string | null;
  thumbnail_is_placeholder: boolean;
}

export interface BackendPropagationEdge {
  from_node: string;
  to_node: string;
  edge_type: string;
}

export interface BackendEvent {
  timestamp: string;
  agent: string;
  action: string;
  detail?: string | null;
  stage?: string | null;
  progress?: number | null;
}

export interface BackendInvestigation {
  id: string;
  state: string;
  media_type: 'image' | 'video';
  original_filename: string;
  demo_mode: boolean;
  verdict?: string | null;
  confidence_label?: string | null;
  overall_score?: number | null;
  error_message?: string | null;
  source_count: number;
  created_at: string;
  updated_at: string;
}

export interface BackendInvestigationDetail extends BackendInvestigation {
  media_asset?: BackendMediaAsset | null;
  forensic_results?: BackendForensicResult | null;
  ai_detection?: BackendAIDetection | null;
  sources: BackendSource[];
  propagation_edges: BackendPropagationEdge[];
  events: BackendEvent[];
}

export interface BackendStatusResponse {
  state: string;
  error_message: string | null;
  events: BackendEvent[];
}

export interface BackendGraphEdge {
  from: string;
  to: string;
  type: string;
}

export interface BackendGraphResponse {
  nodes: {
    id: string;
    type: string;
    platform?: string | null;
    url?: string | null;
    timestamp?: string | null;
    similarity_score?: number | null;
    evidence_confidence?: number | null;
  }[];
  edges: BackendGraphEdge[];
}

export interface BackendStats {
  total_investigations: number;
  ai_generated: number;
  ai_altered: number;
  authentic: number;
  inconclusive: number;
  sources_traced: number;
}

// ---------------------------------------------------------------------
// NORMALIZATION HELPERS
// backend response -> frontend model. Keep all "what does the backend
// call this" knowledge in this file so screens/services stay simple.
// ---------------------------------------------------------------------

const VERDICT_MAP: Record<string, Verdict> = {
  AI_GENERATED: 'AI Generated',
  AI_ALTERED: 'AI Altered',
  LIKELY_AUTHENTIC: 'Likely Authentic',
  INCONCLUSIVE: 'Inconclusive',
  NOT_AVAILABLE: 'Analysis Unavailable',
};

export function mapVerdict(backendVerdict: string | null | undefined): Verdict {
  if (!backendVerdict) return 'Inconclusive';
  return VERDICT_MAP[backendVerdict] ?? 'Analysis Unavailable';
}

export function mapStatus(state: string): InvestigationStatus {
  if (state === 'COMPLETED' || state === 'PARTIAL') return 'completed';
  if (state === 'FAILED') return 'failed';
  return 'processing';
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return 'Unknown size';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatResolution(width?: number | null, height?: number | null): string {
  if (!width || !height) return 'Unknown resolution';
  return `${width} × ${height}`;
}

export function formatDate(iso: string): string {
  try {
    const date = new Date(iso);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();
    const time = date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    if (isToday) return `Today, ${time}`;
    if (isYesterday) return `Yesterday, ${time}`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
}

/**
 * Maps a backend investigation (list or detail form) into the frontend
 * `Investigation` shape. `thumbnailUrl` is passed in separately because
 * building it requires knowing the API base URL (see services/api.ts).
 */
export function mapInvestigation(
  inv: BackendInvestigation | BackendInvestigationDetail,
  thumbnailUrl: string,
): Investigation {
  const detail = inv as BackendInvestigationDetail;
  return {
    id: inv.id,
    filename: inv.original_filename,
    type: inv.media_type,
    thumbnail: thumbnailUrl,
    verdict: mapVerdict(inv.verdict),
    confidence: inv.overall_score != null ? Math.round(inv.overall_score * 100) : 0,
    sourceCount: inv.source_count ?? detail.sources?.length ?? 0,
    date: formatDate(inv.created_at),
    createdAt: inv.created_at,
    resolution: formatResolution(detail.media_asset?.width, detail.media_asset?.height),
    fileSize: formatBytes(detail.media_asset?.size_bytes),
    status: mapStatus(inv.state),
    rawState: inv.state,
    errorMessage: inv.error_message,
  };
}

export function mapAIDetection(detection: BackendAIDetection): AIDetectionDetails {
  return {
    classification: mapVerdict(detection.classification),
    probability: Math.round(detection.probability * 100),
    confidence: detection.confidence,
    modelName: detection.model_name,
    signals: detection.signals ?? [],
    isDemo: detection.is_demo,
    detectorStatus: detection.detector_status,
  };
}

export function mapForensics(forensics: BackendForensicResult): ForensicDetails {
  const metrics: ForensicMetric[] = [];
  if (forensics.ela_score != null) {
    const pct = Math.round(forensics.ela_score * 100);
    metrics.push({ label: 'Error Level Analysis', value: `${pct} / 100`, pct, status: pct > 60 ? 'Compression anomaly' : 'Within normal range' });
  }
  if (forensics.noise_score != null) {
    const pct = Math.round(forensics.noise_score * 100);
    metrics.push({ label: 'Noise Analysis', value: `${pct} / 100`, pct, status: pct > 60 ? 'Irregular noise' : 'Consistent noise pattern' });
  }
  if (forensics.resampling_score != null) {
    const pct = Math.round(forensics.resampling_score * 100);
    metrics.push({ label: 'Resampling Detection', value: `${pct} / 100`, pct, status: pct > 60 ? 'Resampling artifacts' : 'No resampling detected' });
  }
  return {
    forensicScore: forensics.forensic_score != null ? Math.round(forensics.forensic_score * 100) : null,
    elaScore: forensics.ela_score ?? null,
    noiseScore: forensics.noise_score ?? null,
    resamplingScore: forensics.resampling_score ?? null,
    suspiciousIndicators: forensics.suspicious_indicators ?? [],
    metrics,
  };
}

export function mapMetadata(asset: BackendMediaAsset): MetadataDetails {
  const raw = (asset.metadata_json ?? null) as Record<string, unknown> | null;
  const cameraInfo = raw && typeof raw === 'object' ? (raw['camera'] as string | undefined) ?? (raw['Model'] as string | undefined) ?? null : null;
  const editingSoftware = raw && typeof raw === 'object' ? (raw['software'] as string | undefined) ?? (raw['Software'] as string | undefined) ?? null : null;
  return {
    sha256: asset.sha256 || null,
    sizeBytes: asset.size_bytes ?? null,
    mimeType: asset.mime_type ?? null,
    width: asset.width ?? null,
    height: asset.height ?? null,
    durationSeconds: asset.duration_seconds ?? null,
    gpsPresent: !!asset.gps_present,
    cameraInfo: cameraInfo ?? null,
    editingSoftware: editingSoftware ?? null,
    raw,
  };
}

const MATCH_CATEGORY_MAP: Record<string, SourceMatch['match']> = {
  exact: 'Exact Match',
  near_identical: 'Near Duplicate',
  modified_copy: 'Similar Image',
  possibly_related: 'Related',
};

export function mapSource(source: BackendSource): SourceMatch {
  let domain = source.domain ?? '';
  if (!domain) {
    try {
      domain = new URL(source.url).hostname;
    } catch {
      domain = source.url;
    }
  }
  const confidencePct = source.source_confidence != null ? Math.round(source.source_confidence * 100) : null;
  const confidenceLabel = confidencePct == null ? 'Unknown' : confidencePct >= 90 ? 'Very high' : confidencePct >= 70 ? 'High' : confidencePct >= 40 ? 'Medium' : 'Low';
  return {
    id: source.id,
    title: source.title || domain || 'Untitled source',
    domain,
    date: source.publication_date || 'Unknown date',
    similarity: source.similarity_score != null ? Math.round(source.similarity_score * 100) : 0,
    confidence: confidenceLabel,
    match: (source.match_category && MATCH_CATEGORY_MAP[source.match_category]) || (source.classification === 'LIKELY_EARLIEST_FOUND_SOURCE' ? 'Possible Origin' : 'Related'),
    thumbnail: source.thumbnail_url || '',
    url: source.url,
    accessible: source.accessible,
  };
}

const STAGE_ICONS: Record<string, string> = {
  UPLOADED: 'cloud-upload-outline',
  HASHING: 'check-decagram-outline',
  METADATA_ANALYSIS: 'file-cog-outline',
  AI_ANALYSIS: 'creation',
  FORENSIC_ANALYSIS: 'shield-search-outline',
  ORIGIN_SEARCH: 'source-branch',
  SOURCE_VERIFICATION: 'source-branch',
  PROPAGATION_ANALYSIS: 'graph-outline',
  CORRELATION: 'link-variant',
  REPORT_GENERATION: 'file-document-outline',
  COMPLETED: 'check-circle-outline',
  FAILED: 'alert-circle-outline',
};

export function mapTimelineEntry(event: BackendEvent): TimelineEntry {
  const time = (() => {
    try {
      return new Date(event.timestamp).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    } catch {
      return event.timestamp;
    }
  })();
  return {
    title: event.action,
    agent: formatAgentName(event.agent),
    description: event.detail || '',
    time,
    stage: event.stage,
    icon: (event.stage && STAGE_ICONS[event.stage]) || 'information-outline',
  };
}

export function formatAgentName(agent: string): string {
  return agent
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function mapPropagationGraph(graph: BackendGraphResponse): PropagationGraph {
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      platform: n.platform ?? null,
      url: n.url ?? null,
      timestamp: n.timestamp ?? null,
      similarityScore: n.similarity_score ?? null,
      evidenceConfidence: n.evidence_confidence ?? null,
    })),
    edges: graph.edges.map((e) => ({ from: e.from, to: e.to, type: e.type })),
  };
}

export function mapInsights(stats: BackendStats, investigations: Investigation[]): InsightsSummary {
  const withConfidence = investigations.filter((i) => i.status === 'completed' && i.confidence > 0);
  const averageConfidence = withConfidence.length
    ? Math.round(withConfidence.reduce((sum, i) => sum + i.confidence, 0) / withConfidence.length)
    : null;
  return {
    totalInvestigations: stats.total_investigations,
    aiGenerated: stats.ai_generated,
    aiAltered: stats.ai_altered,
    authentic: stats.authentic,
    inconclusive: stats.inconclusive,
    sourcesTraced: stats.sources_traced,
    averageConfidence,
  };
}

/** Backend stage progression, used to build the pipeline UI even before individual stage events arrive. */
export const STAGE_ORDER = [
  'HASHING',
  'METADATA_ANALYSIS',
  'AI_ANALYSIS',
  'FORENSIC_ANALYSIS',
  'ORIGIN_SEARCH',
  'SOURCE_VERIFICATION',
  'PROPAGATION_ANALYSIS',
  'CORRELATION',
  'REPORT_GENERATION',
] as const;

export const STAGE_PROGRESS: Record<string, number> = {
  HASHING: 10,
  METADATA_ANALYSIS: 20,
  AI_ANALYSIS: 35,
  FORENSIC_ANALYSIS: 50,
  ORIGIN_SEARCH: 65,
  SOURCE_VERIFICATION: 75,
  PROPAGATION_ANALYSIS: 85,
  CORRELATION: 92,
  REPORT_GENERATION: 97,
  COMPLETED: 100,
};

export const STAGE_LABELS: Record<string, string> = {
  HASHING: 'Evidence Processing',
  METADATA_ANALYSIS: 'Metadata Analysis',
  AI_ANALYSIS: 'AI Detection',
  FORENSIC_ANALYSIS: 'Image Forensics',
  ORIGIN_SEARCH: 'Source Discovery',
  SOURCE_VERIFICATION: 'Source Verification',
  PROPAGATION_ANALYSIS: 'Propagation Analysis',
  CORRELATION: 'Correlation',
  REPORT_GENERATION: 'Report Generation',
};
