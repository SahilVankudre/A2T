/**
 * TypeScript types — mirrors backend schemas.py exactly.
 *
 * Depends on:  nothing
 * Depended by: api.ts, websocket.ts, every component
 */

// ── Job status enum ──────────────────────────────────────

export type JobStatus =
  | "pending"
  | "preprocessing"
  | "transcribing"
  | "formatting"
  | "completed"
  | "failed";

// ── Transcription data ───────────────────────────────────

export interface Word {
  word: string;
  start: number;
  end: number;
  probability: number;
}

export interface Segment {
  id: number;
  start: number;
  end: number;
  text: string;
  words: Word[];
  avg_logprob: number;
  no_speech_prob: number;
}

// ── Job responses ────────────────────────────────────────

export interface JobCreateResponse {
  job_id: string;
  status: JobStatus;
  websocket_url: string;
  created_at: string;
}

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  original_filename: string;
  file_size_bytes: number | null;

  // Audio metadata
  duration_sec: number | null;
  sample_rate: number | null;

  // Config used
  model_name: string;
  language: string | null;
  beam_size: number;

  // Results (populated when status=completed)
  language_detected: string | null;
  language_probability: number | null;
  processing_sec: number | null;
  rtf: number | null;
  result_text: string | null;
  segment_count: number | null;
  segments: Segment[] | null;

  // Error
  error_message: string | null;

  // Timestamps
  created_at: string;
  completed_at: string | null;
}

export interface JobListResponse {
  jobs: JobResponse[];
  total: number;
  page: number;
  per_page: number;
}

// ── WebSocket messages ───────────────────────────────────

export interface WSProgressMessage {
  type: "progress";
  stage: JobStatus;
  progress: number; // 0.0 - 1.0
  message: string;
}

export interface WSCompletedMessage {
  type: "completed";
  job: JobResponse;
}

export interface WSErrorMessage {
  type: "error";
  error: string;
  stage: string;
}

export type WSMessage = WSProgressMessage | WSCompletedMessage | WSErrorMessage;

// ── Model info ───────────────────────────────────────────

export interface ModelInfo {
  name: string;
  compute_type: string;
  vram_gb: number;
  description: string;
  is_loaded: boolean;
}

export interface ModelListResponse {
  models: ModelInfo[];
  active_model: string;
}

// ── Health check ─────────────────────────────────────────

export interface HealthResponse {
  status: "healthy" | "degraded";
  model_loaded: boolean;
  model_name: string | null;
  gpu_available: boolean;
  gpu_name: string | null;
  vram_total_gb: number | null;
  database_connected: boolean;
}

// ── Error response ───────────────────────────────────────

export interface ErrorResponse {
  error: string;
  detail: string | null;
}

// ── App state (used by page.tsx) ─────────────────────────

export type AppView = "upload" | "processing" | "results";

export interface AppState {
  view: AppView;
  jobId: string | null;
  job: JobResponse | null;
}