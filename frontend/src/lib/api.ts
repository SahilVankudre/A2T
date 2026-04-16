/**
 * REST API client — typed functions for every backend endpoint.
 *
 * All paths are relative (e.g., "/api/...") so Next.js rewrites
 * proxy them to the backend on port 8000 automatically.
 *
 * Depends on:  types.ts (F03)
 * Depended by: upload-zone.tsx (F06), export-panel.tsx (F11), page.tsx (F09)
 */

import type {
  JobCreateResponse,
  JobResponse,
  JobListResponse,
  ModelListResponse,
  HealthResponse,
  ErrorResponse,
} from "./types";

// ── Error handling ───────────────────────────────────────

export class ApiError extends Error {
  status: number;
  detail: string | null;

  constructor(status: number, error: string, detail: string | null = null) {
    super(error);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: ErrorResponse | null = null;
    try {
      body = await res.json();
    } catch {
      // Response wasn't JSON
    }
    throw new ApiError(
      res.status,
      body?.error ?? `Request failed (${res.status})`,
      body?.detail ?? null
    );
  }
  return res.json();
}

// ── Upload options ───────────────────────────────────────

export interface UploadOptions {
  model?: string;
  language?: string | null;
  beam_size?: number;
  vad_filter?: boolean;
  initial_prompt?: string | null;
}

// ── API functions ────────────────────────────────────────

/** Upload an audio file and start transcription. Returns immediately with job_id. */
export async function uploadAudio(
  file: File,
  options: UploadOptions = {}
): Promise<JobCreateResponse> {
  const form = new FormData();
  form.append("file", file);

  if (options.model) form.append("model", options.model);
  if (options.language) form.append("language", options.language);
  if (options.beam_size !== undefined) form.append("beam_size", String(options.beam_size));
  if (options.vad_filter !== undefined) form.append("vad_filter", String(options.vad_filter));
  if (options.initial_prompt) form.append("initial_prompt", options.initial_prompt);

  const res = await fetch("/api/transcribe", { method: "POST", body: form });
  return handleResponse<JobCreateResponse>(res);
}

/** Get full job detail including segments (if completed). */
export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`/api/jobs/${jobId}`);
  return handleResponse<JobResponse>(res);
}

/** List recent jobs with pagination and optional status filter. */
export async function listJobs(
  page = 1,
  perPage = 20,
  status?: string
): Promise<JobListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (status) params.set("status", status);

  const res = await fetch(`/api/jobs?${params}`);
  return handleResponse<JobListResponse>(res);
}

/** Delete a job and its files. */
export async function deleteJob(jobId: string): Promise<void> {
  const res = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.error ?? `Delete failed (${res.status})`,
      body?.detail ?? null
    );
  }
}

/** Get the download URL for a specific output format. */
export function getDownloadUrl(jobId: string, format: "txt" | "srt" | "vtt" | "json"): string {
  return `/api/jobs/${jobId}/download?format=${format}`;
}

/** Get the audio file URL (for wavesurfer.js player). */
export function getAudioUrl(jobId: string): string {
  return `/api/jobs/${jobId}/audio`;
}

/** List available ASR models and which one is loaded. */
export async function getModels(): Promise<ModelListResponse> {
  const res = await fetch("/api/models");
  return handleResponse<ModelListResponse>(res);
}

/** System health check — GPU, model, database status. */
export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  return handleResponse<HealthResponse>(res);
}

/** Upload the bundled sample audio file. */
export async function uploadSample(options: UploadOptions = {}): Promise<JobCreateResponse> {
  const res = await fetch("/sample.wav");
  const blob = await res.blob();
  const file = new File([blob], "sample.wav", { type: "audio/wav" });
  return uploadAudio(file, options);
}