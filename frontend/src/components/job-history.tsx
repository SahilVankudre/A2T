/**
 * Job history — slide-out panel showing all past transcription jobs.
 *
 * Click any completed job to view its results. Delete jobs to clean up.
 * Fetches the job list when the panel opens and auto-refreshes.
 *
 * Depends on:  types.ts (F03), api.ts (F04)
 * Depended by: page.tsx (F09)
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import { X, FileAudio, Trash2, Loader2, CheckCircle2, XCircle, Clock, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { listJobs, deleteJob } from "@/lib/api";
import type { JobResponse } from "@/lib/types";

// ── Helpers ──────────────────────────────────────────────

function formatDate(isoString: string): string {
  const d = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function statusIcon(status: string) {
  switch (status) {
    case "completed": return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
    case "failed": return <XCircle className="h-3.5 w-3.5 text-red-500" />;
    default: return <Clock className="h-3.5 w-3.5 text-yellow-500 animate-pulse" />;
  }
}

function statusBadge(status: string) {
  const variants: Record<string, string> = {
    completed: "bg-green-500/10 text-green-600 border-green-500/20",
    failed: "bg-red-500/10 text-red-600 border-red-500/20",
    pending: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
    preprocessing: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    transcribing: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    formatting: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  };
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${variants[status] || ""}`}>
      {status}
    </span>
  );
}

// ── Props ────────────────────────────────────────────────

interface JobHistoryProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectJob: (job: JobResponse) => void;
  currentJobId: string | null;
}

// ── Component ────────────────────────────────────────────

export function JobHistory({ isOpen, onClose, onSelectJob, currentJobId }: JobHistoryProps) {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listJobs(1, 50);
      setJobs(data.jobs);
      setTotal(data.total);
    } catch (err) {
      console.error("Failed to fetch jobs:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on open
  useEffect(() => {
    if (isOpen) fetchJobs();
  }, [isOpen, fetchJobs]);

  const handleDelete = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation();
    if (deletingId) return;
    setDeletingId(jobId);
    try {
      await deleteJob(jobId);
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
      setTotal((prev) => prev - 1);
    } catch (err) {
      console.error("Failed to delete job:", err);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40 transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        className={`
          fixed top-0 right-0 h-full w-full max-w-sm bg-background border-l shadow-xl z-50
          transform transition-transform duration-300 ease-in-out
          ${isOpen ? "translate-x-0" : "translate-x-full"}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div>
            <h2 className="text-sm font-semibold">Transcription History</h2>
            <p className="text-[11px] text-muted-foreground">{total} job{total !== 1 ? "s" : ""}</p>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={fetchJobs} disabled={loading}>
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Job list */}
        <ScrollArea className="h-[calc(100vh-57px)]">
          {loading && jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mb-2" />
              <p className="text-sm">Loading jobs...</p>
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <FileAudio className="h-8 w-8 mb-3 opacity-40" />
              <p className="text-sm">No transcriptions yet</p>
              <p className="text-xs mt-1">Upload an audio file to get started</p>
            </div>
          ) : (
            <div className="flex flex-col">
              {jobs.map((job) => {
                const isActive = job.job_id === currentJobId;
                const isCompleted = job.status === "completed";
                const isDeleting = deletingId === job.job_id;

                return (
                  <div
                    key={job.job_id}
                    onClick={() => isCompleted && onSelectJob(job)}
                    className={`
                      flex items-start gap-3 px-4 py-3 border-b border-border/40
                      transition-colors duration-150
                      ${isActive ? "bg-primary/[0.06]" : ""}
                      ${isCompleted ? "cursor-pointer hover:bg-muted/40" : "opacity-70"}
                    `}
                  >
                    {/* Status icon */}
                    <div className="pt-0.5 flex-shrink-0">
                      {statusIcon(job.status)}
                    </div>

                    {/* Job info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{job.original_filename}</p>
                      <div className="flex items-center gap-2 mt-1">
                        {statusBadge(job.status)}
                        {job.duration_sec && (
                          <span className="text-[11px] text-muted-foreground">
                            {formatDuration(job.duration_sec)}
                          </span>
                        )}
                        {job.language_detected && (
                          <span className="text-[11px] text-muted-foreground uppercase">
                            {job.language_detected}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground/60 mt-1">
                        {formatDate(job.created_at)}
                        {job.segment_count ? ` · ${job.segment_count} segments` : ""}
                      </p>
                    </div>

                    {/* Delete button */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 flex-shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={(e) => handleDelete(e, job.job_id)}
                      disabled={isDeleting}
                    >
                      {isDeleting ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Trash2 className="h-3 w-3" />
                      )}
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </div>
    </>
  );
}