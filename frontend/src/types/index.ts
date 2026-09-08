export type MediaType = "image" | "video";

export interface Investigation {
  id: string;
  state: string;
  media_type: MediaType;
  original_filename: string;
  demo_mode: boolean;
  verdict: string | null;
  confidence_label: string | null;
  overall_score: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface MediaAsset {
  sha256: string;
  size_bytes: number;
  mime_type: string;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  gps_present: boolean;
  phash: string | null;
  dhash: string | null;
  ahash: string | null;
  metadata_json: any;
}

export interface ForensicResult {
  ela_score: number | null;
  noise_score: number | null;
  resampling_score: number | null;
  compression_notes: any;
  suspicious_indicators: string[] | null;
  frame_analysis: any;
  forensic_score: number | null;
}

export interface AIDetection {
  classification: string;
  probability: number;
  confidence: string;
  model_name: string;
  signals: string[] | null;
  is_demo: boolean;
}

export interface SourceItem {
  id: string;
  url: string;
  title: string | null;
  platform: string | null;
  domain: string | null;
  publication_date: string | null;
  date_found: string;
  similarity_score: number | null;
  phash_distance: number | null;
  match_category: string | null;
  source_confidence: number | null;
  classification: string | null;
  reasoning: string[] | null;
  accessible: boolean;
  inaccessible_reason: string | null;
  is_demo: boolean;
}

export interface GraphNode {
  id: string;
  type: string;
  platform: string | null;
  url: string;
  timestamp: string | null;
  similarity_score: number | null;
  evidence_confidence: number | null;
}

export interface GraphEdge {
  from: string;
  to: string;
  type: string;
}

export interface InvestigationDetail extends Investigation {
  media_asset: MediaAsset | null;
  forensic_results: ForensicResult | null;
  ai_detection: AIDetection | null;
  sources: SourceItem[];
  propagation_edges: any[];
  events: EventItem[];
}

export interface EventItem {
  timestamp: string;
  agent: string;
  action: string;
  detail: string | null;
  stage: string | null;
  progress: number | null;
}

export interface Report {
  investigation_id: string;
  generated_at: string;
  executive_summary: { verdict: string; confidence: string; overall_score: number | string };
  evidence_information: Record<string, any>;
  ai_detection: Record<string, any>;
  forensic_findings: Record<string, any>;
  earliest_credible_source: Record<string, any>;
  source_verification: any;
  propagation_timeline: any;
  confidence_assessment: Record<string, any>;
  limitations: string[];
  recommended_human_verification: string;
  what_we_know: string[];
  what_we_suspect: string[];
  what_we_could_not_verify: string[];
}
