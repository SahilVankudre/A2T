/**
 * Export panel — format tabs (TXT/SRT/VTT/JSON) with preview and download.
 *
 * Depends on:  types.ts (F03), api.ts (F04) for getDownloadUrl
 * Depended by: page.tsx (F09)
 */

"use client";

import { useState } from "react";
import { Download, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getDownloadUrl } from "@/lib/api";
import type { JobResponse } from "@/lib/types";

// ── Format preview generators ────────────────────────────

function formatTimeSrt(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")},${ms.toString().padStart(3, "0")}`;
}

function formatTimeVtt(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}.${ms.toString().padStart(3, "0")}`;
}

function generateTxt(job: JobResponse): string {
  return job.result_text ?? "";
}

function generateSrt(job: JobResponse): string {
  if (!job.segments) return "";
  return job.segments
    .map((seg, i) => `${i + 1}\n${formatTimeSrt(seg.start)} --> ${formatTimeSrt(seg.end)}\n${seg.text}`)
    .join("\n\n");
}

function generateVtt(job: JobResponse): string {
  if (!job.segments) return "WEBVTT";
  const cues = job.segments
    .map((seg, i) => `${i + 1}\n${formatTimeVtt(seg.start)} --> ${formatTimeVtt(seg.end)}\n${seg.text}`)
    .join("\n\n");
  return `WEBVTT\n\n${cues}`;
}

function generateJson(job: JobResponse): string {
  if (!job.segments) return "{}";
  const data = {
    language: job.language_detected,
    duration: job.duration_sec,
    model: job.model_name,
    segments: job.segments.map((s) => ({
      id: s.id, start: s.start, end: s.end, text: s.text,
      avg_logprob: s.avg_logprob,
      words: s.words?.length ? s.words : undefined,
    })),
  };
  return JSON.stringify(data, null, 2);
}

interface ExportPanelProps {
  job: JobResponse;
}

export function ExportPanel({ job }: ExportPanelProps) {
  const [copiedTab, setCopiedTab] = useState<string | null>(null);

  const formats = [
    { key: "txt" as const, label: "TXT", content: generateTxt(job) },
    { key: "srt" as const, label: "SRT", content: generateSrt(job) },
    { key: "vtt" as const, label: "VTT", content: generateVtt(job) },
    { key: "json" as const, label: "JSON", content: generateJson(job) },
  ];

  const wordCount = job.result_text ? job.result_text.split(/\s+/).filter(Boolean).length : 0;

  const handleCopy = async (content: string, key: string) => {
    try {
      await navigator.clipboard.writeText(content);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopiedTab(key);
    setTimeout(() => setCopiedTab(null), 2000);
  };

  return (
    <Card className="p-0 overflow-hidden">
      <Tabs defaultValue="txt" className="w-full">
        <div className="flex items-center justify-between border-b px-4 py-2 gap-2">
          <div className="flex items-center gap-3">
            <TabsList className="h-8">
              {formats.map((f) => (
                <TabsTrigger key={f.key} value={f.key} className="text-xs px-3 h-7">
                  {f.label}
                </TabsTrigger>
              ))}
            </TabsList>
            {wordCount > 0 && (
              <span className="text-[11px] text-muted-foreground">{wordCount} words</span>
            )}
          </div>

          <div className="flex gap-1">
            {formats.map((f) => (
              <Button key={f.key} variant="ghost" size="sm" className="h-7 text-xs gap-1.5" asChild>
                <a href={getDownloadUrl(job.job_id, f.key)} download>
                  <Download className="h-3 w-3" />
                  {f.label}
                </a>
              </Button>
            ))}
          </div>
        </div>

        {formats.map((f) => (
          <TabsContent key={f.key} value={f.key} className="mt-0">
            <div className="relative">
              <Button
                variant="ghost"
                size="sm"
                className="absolute top-2 right-2 h-7 text-xs gap-1.5 z-10"
                onClick={() => handleCopy(f.content, f.key)}
              >
                {copiedTab === f.key ? (
                  <><Check className="h-3 w-3" /> Copied</>
                ) : (
                  <><Copy className="h-3 w-3" /> Copy</>
                )}
              </Button>
              <pre className="p-4 pr-20 text-xs font-mono text-muted-foreground leading-relaxed max-h-[300px] overflow-auto whitespace-pre-wrap break-words">
                {f.content || "No content available"}
              </pre>
            </div>
          </TabsContent>
        ))}
      </Tabs>
    </Card>
  );
}