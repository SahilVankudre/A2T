/**
 * Main page — state machine: Upload → Processing → Results.
 *
 * Features: WebSocket live progress, polling fallback, job history panel.
 * Click any past job in history to view its results and download exports.
 */

"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { RotateCcw, AudioLines, FileAudio, History, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useWebSocket } from "@/lib/websocket";
import { getJob } from "@/lib/api";
import type { AppView, JobResponse, JobCreateResponse } from "@/lib/types";

import { UploadZone } from "@/components/upload-zone";
import { ProcessingView } from "@/components/processing-view";
import { TranscriptView } from "@/components/transcript-view";
import { StatsBar } from "@/components/stats-bar";
import { ExportPanel } from "@/components/export-panel";
import { JobHistory } from "@/components/job-history";

export default function Home() {
  const [view, setView] = useState<AppView>("upload");
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [filename, setFilename] = useState("");
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [loadingPastJob, setLoadingPastJob] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const ws = useWebSocket(view === "processing" ? jobId : null);

  // ── Transition to results ──────────────────────────────

  const showResults = useCallback((jobData: JobResponse) => {
    setJob(jobData);
    setJobId(jobData.job_id);
    setFilename(jobData.original_filename);
    setView("results");
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  // ── WebSocket completed → show results ─────────────────

  useEffect(() => {
    if (ws.job && ws.job.status === "completed") showResults(ws.job);
  }, [ws.job, showResults]);

  // ── Polling fallback ───────────────────────────────────

  useEffect(() => {
    if (view !== "processing" || !jobId) return;

    pollRef.current = setInterval(async () => {
      try {
        const data = await getJob(jobId);
        if (data.status === "completed") {
          showResults(data);
        } else if (data.status === "failed") {
          setJob(data);
          setView("results");
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch { /* WS is primary */ }
    }, 2000);

    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [view, jobId, showResults]);

  // ── Upload complete → processing ───────────────────────

  const handleUploadComplete = useCallback((response: JobCreateResponse, name: string) => {
    setJobId(response.job_id);
    setFilename(name);
    setView("processing");
  }, []);

  // ── Load a past job from history ───────────────────────

  const handleSelectPastJob = useCallback(async (selectedJob: JobResponse) => {
    setIsHistoryOpen(false);

    // If the selected job already has segments, show directly
    if (selectedJob.segments && selectedJob.segments.length > 0) {
      showResults(selectedJob);
      return;
    }

    // Otherwise fetch full job with segments from backend
    setLoadingPastJob(true);
    try {
      const fullJob = await getJob(selectedJob.job_id);
      showResults(fullJob);
    } catch (err) {
      console.error("Failed to load job:", err);
    } finally {
      setLoadingPastJob(false);
    }
  }, [showResults]);

  // ── Reset ──────────────────────────────────────────────

  const handleReset = useCallback(() => {
    setView("upload");
    setJobId(null);
    setJob(null);
    setFilename("");
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-30">
        <div className="max-w-5xl mx-auto flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary flex items-center justify-center">
              <AudioLines className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-lg font-semibold leading-none tracking-tight">A2T</h1>
              <p className="text-[11px] text-muted-foreground mt-0.5">Audio-to-text transcription</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {view !== "upload" && (
              <Button variant="outline" size="sm" onClick={handleReset} className="gap-2 text-xs">
                <RotateCcw className="h-3 w-3" />
                New
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsHistoryOpen(true)}
              className="gap-2 text-xs"
            >
              <History className="h-3.5 w-3.5" />
              History
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Loading overlay for past job fetch */}
        {loadingPastJob && (
          <div className="flex flex-col items-center justify-center py-24">
            <Loader2 className="h-8 w-8 animate-spin text-primary mb-3" />
            <p className="text-sm text-muted-foreground">Loading transcription...</p>
          </div>
        )}

        {/* Upload view */}
        {!loadingPastJob && view === "upload" && (
          <div className="pt-16 pb-12">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold tracking-tight mb-3">Transcribe audio to text</h2>
              <p className="text-muted-foreground text-base max-w-md mx-auto">
                Upload any audio file and get accurate, timestamped transcriptions
                with confidence scores — powered by Whisper AI.
              </p>
            </div>
            <UploadZone onUploadComplete={handleUploadComplete} />
          </div>
        )}

        {/* Processing view */}
        {!loadingPastJob && view === "processing" && (
          <div className="pt-12">
            <ProcessingView ws={ws} filename={filename || "Audio file"} />
            {ws.error && (
              <div className="flex flex-col items-center gap-3 mt-6">
                <div className="px-4 py-3 rounded-lg bg-destructive/10 text-destructive text-sm max-w-md text-center">
                  {ws.error}
                </div>
                <Button variant="outline" size="sm" onClick={handleReset} className="gap-2">
                  <RotateCcw className="h-3 w-3" /> Try again
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Results view — completed */}
        {!loadingPastJob && view === "results" && job && job.status === "completed" && (
          <div className="flex flex-col gap-5">
            <div className="flex items-center gap-3 py-1">
              <FileAudio className="h-5 w-5 text-muted-foreground" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{job.original_filename}</p>
                <p className="text-xs text-muted-foreground">Transcription complete</p>
              </div>
            </div>

            <StatsBar job={job} />
            <TranscriptView job={job} />
            <Separator />
            <div>
              <h3 className="text-sm font-medium mb-3">Export transcription</h3>
              <ExportPanel job={job} />
            </div>
          </div>
        )}

        {/* Results view — failed */}
        {!loadingPastJob && view === "results" && job && job.status === "failed" && (
          <div className="pt-12 flex flex-col items-center gap-4">
            <div className="max-w-md w-full p-5 rounded-lg bg-destructive/10 text-destructive text-sm">
              <p className="font-medium mb-1">Transcription failed</p>
              <p className="opacity-80">{job.error_message || "An unknown error occurred."}</p>
            </div>
            <Button variant="outline" size="sm" onClick={handleReset} className="gap-2">
              <RotateCcw className="h-3 w-3" /> Try again
            </Button>
          </div>
        )}
      </main>

      {/* Job History panel */}
      <JobHistory
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        onSelectJob={handleSelectPastJob}
        currentJobId={jobId}
      />
    </div>
  );
}