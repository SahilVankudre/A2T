/**
 * Stats bar — horizontal display of transcription metrics.
 *
 * Shows duration, processing time, RTF, language, model, and confidence
 * in a compact row at the top of the results view.
 *
 * Depends on:  types.ts (F03)
 * Depended by: page.tsx (F09)
 */

"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { JobResponse } from "@/lib/types";

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

interface StatItemProps {
  label: string;
  value: string;
}

function StatItem({ label, value }: StatItemProps) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-3">
      <span className="text-[11px] text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className="text-sm font-medium font-mono">{value}</span>
    </div>
  );
}

interface StatsBarProps {
  job: JobResponse;
}

export function StatsBar({ job }: StatsBarProps) {
  return (
    <Card className="flex items-center justify-between px-2 py-3 overflow-x-auto gap-1">
      <StatItem
        label="Duration"
        value={job.duration_sec ? formatDuration(job.duration_sec) : "—"}
      />
      <div className="h-6 w-px bg-border flex-shrink-0" />
      <StatItem
        label="Processing"
        value={job.processing_sec ? formatDuration(job.processing_sec) : "—"}
      />
      <div className="h-6 w-px bg-border flex-shrink-0" />
      <StatItem
        label="RTF"
        value={job.rtf ? `${job.rtf.toFixed(3)}x` : "—"}
      />
      <div className="h-6 w-px bg-border flex-shrink-0" />
      <StatItem
        label="Language"
        value={job.language_detected?.toUpperCase() ?? "—"}
      />
      <div className="h-6 w-px bg-border flex-shrink-0" />
      <StatItem
        label="Confidence"
        value={job.language_probability ? `${(job.language_probability * 100).toFixed(0)}%` : "—"}
      />
      <div className="h-6 w-px bg-border flex-shrink-0" />
      <StatItem
        label="Model"
        value={job.model_name}
      />
    </Card>
  );
}