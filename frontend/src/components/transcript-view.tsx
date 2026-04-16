/**
 * Transcript view — audio waveform player + segmented transcript with click-to-seek.
 *
 * Features: waveform visualization, click-to-seek, active segment tracking,
 * auto-scroll, playback speed control, keyboard shortcuts, confidence dots.
 *
 * Depends on:  types.ts (F03), api.ts (F04) for getAudioUrl
 * Depended by: page.tsx (F09)
 */

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Play, Pause, RotateCcw, Gauge, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getAudioUrl } from "@/lib/api";
import type { Segment, JobResponse } from "@/lib/types";

// ── Helpers ──────────────────────────────────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatTimeFull(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 100);
  return `${m}:${s.toString().padStart(2, "0")}.${ms.toString().padStart(2, "0")}`;
}

function ConfidenceDot({ logprob }: { logprob: number }) {
  const color =
    logprob > -0.4 ? "bg-green-500" :
    logprob > -0.8 ? "bg-yellow-500" :
    "bg-red-500";
  return <span className={`inline-block h-2 w-2 rounded-full ${color} flex-shrink-0`} />;
}

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2];

interface TranscriptViewProps {
  job: JobResponse;
}

export function TranscriptView({ job }: TranscriptViewProps) {
  const segments = job.segments ?? [];
  const duration = job.duration_sec ?? 0;

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [isReady, setIsReady] = useState(false);
  const [activeSegmentId, setActiveSegmentId] = useState<number | null>(null);
  const [playbackRate, setPlaybackRate] = useState(1);

  const waveformRef = useRef<HTMLDivElement>(null);
  const wavesurferRef = useRef<any>(null);
  const initRef = useRef(false);
  const segmentRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  // ── Initialize wavesurfer (Strict Mode safe) ───────────

  useEffect(() => {
    if (!waveformRef.current || initRef.current) return;
    initRef.current = true;

    let ws: any = null;
    let destroyed = false;

    async function init() {
      const WaveSurfer = (await import("wavesurfer.js")).default;
      if (destroyed || !waveformRef.current) return;

      ws = WaveSurfer.create({
        container: waveformRef.current,
        url: getAudioUrl(job.job_id),
        height: 56,
        barWidth: 2,
        barGap: 1,
        barRadius: 2,
        cursorWidth: 2,
        waveColor: "hsl(var(--muted-foreground) / 0.25)",
        progressColor: "hsl(var(--primary))",
        cursorColor: "hsl(var(--primary) / 0.7)",
      });

      ws.on("ready", () => { if (!destroyed) setIsReady(true); });
      ws.on("timeupdate", (t: number) => { if (!destroyed) setCurrentTime(t); });
      ws.on("play", () => { if (!destroyed) setIsPlaying(true); });
      ws.on("pause", () => { if (!destroyed) setIsPlaying(false); });
      ws.on("finish", () => {
        if (!destroyed) { setIsPlaying(false); setCurrentTime(0); }
      });

      wavesurferRef.current = ws;
    }

    init();

    return () => {
      destroyed = true;
      initRef.current = false;
      if (ws) ws.destroy();
      wavesurferRef.current = null;
    };
  }, [job.job_id]);

  // ── Track active segment ───────────────────────────────

  useEffect(() => {
    if (!segments.length) return;
    const active = segments.find((seg) => currentTime >= seg.start && currentTime < seg.end);
    const newId = active?.id ?? null;
    if (newId !== activeSegmentId) {
      setActiveSegmentId(newId);
      if (newId !== null && isPlaying) {
        segmentRefs.current.get(newId)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [currentTime, segments, activeSegmentId, isPlaying]);

  // ── Keyboard shortcuts ─────────────────────────────────

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === "Space") { e.preventDefault(); wavesurferRef.current?.playPause(); }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  // ── Controls ───────────────────────────────────────────

  const togglePlayPause = useCallback(() => { wavesurferRef.current?.playPause(); }, []);

  const seekToSegment = useCallback((segment: Segment) => {
    const ws = wavesurferRef.current;
    if (!ws || !duration) return;
    ws.seekTo(segment.start / duration);
    ws.play();
  }, [duration]);

  const restart = useCallback(() => {
    const ws = wavesurferRef.current;
    if (!ws) return;
    ws.seekTo(0);
    ws.play();
  }, []);

  const cycleSpeed = useCallback(() => {
    setPlaybackRate((prev) => {
      const idx = SPEED_OPTIONS.indexOf(prev);
      const next = SPEED_OPTIONS[(idx + 1) % SPEED_OPTIONS.length];
      if (wavesurferRef.current) wavesurferRef.current.setPlaybackRate(next);
      return next;
    });
  }, []);

  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="flex flex-col gap-4 w-full">
      {/* Waveform player */}
      <Card className="p-4 pb-3">
        <div className="relative">
          <div ref={waveformRef} className="w-full min-h-[56px]" />
          {!isReady && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/80">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              <span className="ml-2 text-xs text-muted-foreground">Loading waveform...</span>
            </div>
          )}
        </div>

        {/* Thin progress line */}
        <div className="w-full h-0.5 bg-muted rounded-full mt-2 overflow-hidden">
          <div className="h-full bg-primary transition-all duration-200" style={{ width: `${progressPct}%` }} />
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 mt-2.5">
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={togglePlayPause} disabled={!isReady}>
            {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5 ml-0.5" />}
          </Button>

          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={restart} disabled={!isReady}>
            <RotateCcw className="h-3 w-3" />
          </Button>

          <Button variant="ghost" size="sm" className="h-8 px-2 text-xs font-mono gap-1" onClick={cycleSpeed} disabled={!isReady}>
            <Gauge className="h-3 w-3" />
            {playbackRate}x
          </Button>

          <span className="text-xs font-mono text-muted-foreground ml-1">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>

          <span className="ml-auto text-[11px] text-muted-foreground/60">
            {segments.length} segments
          </span>
        </div>
      </Card>

      {/* Transcript segments */}
      <Card className="p-0 overflow-hidden">
        <ScrollArea className="h-[420px]">
          <div className="flex flex-col">
            {segments.map((segment) => {
              const isActive = segment.id === activeSegmentId;
              return (
                <div
                  key={segment.id}
                  ref={(el) => { if (el) segmentRefs.current.set(segment.id, el); }}
                  onClick={() => seekToSegment(segment)}
                  className={`
                    flex gap-3 px-4 py-3 cursor-pointer transition-all duration-150
                    border-b border-border/40
                    ${isActive
                      ? "bg-primary/[0.06] border-l-[3px] border-l-primary"
                      : "hover:bg-muted/40 border-l-[3px] border-l-transparent"
                    }
                  `}
                >
                  <div className="flex flex-col items-end gap-1.5 min-w-[68px] flex-shrink-0 pt-0.5">
                    <span className={`text-[11px] font-mono ${isActive ? "text-primary font-medium" : "text-muted-foreground"}`}>
                      {formatTimeFull(segment.start)}
                    </span>
                    <ConfidenceDot logprob={segment.avg_logprob} />
                  </div>
                  <p className={`text-sm leading-relaxed flex-1 ${isActive ? "text-foreground" : "text-foreground/75"}`}>
                    {segment.text}
                  </p>
                </div>
              );
            })}
            {segments.length === 0 && (
              <div className="px-4 py-12 text-center text-sm text-muted-foreground">
                No segments found in this transcription.
              </div>
            )}
          </div>
        </ScrollArea>
      </Card>

      {/* Confidence legend */}
      <div className="flex items-center gap-4 text-[11px] text-muted-foreground/70 px-1">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> High confidence
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-yellow-500" /> Medium
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500" /> Low
        </span>
      </div>
    </div>
  );
}