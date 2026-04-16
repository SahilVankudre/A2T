/**
 * Processing view — live stage-by-stage pipeline progress.
 *
 * Receives WebSocket state from the parent and renders each pipeline
 * stage with the appropriate visual state (pending, active, done, failed).
 * The "transcribing" stage shows real per-segment progress from the GPU.
 *
 * Depends on:  types.ts (F03), websocket.ts (F05) for WSState type
 * Depended by: page.tsx (F09)
 */

"use client";

import { Check, Loader2, AlertCircle, AudioLines, FileText, AudioWaveform } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { JobStatus } from "@/lib/types";
import type { WSState } from "@/lib/websocket";

// ── Pipeline stage definitions ───────────────────────────

interface StageInfo {
  key: JobStatus;
  label: string;
  description: string;
  icon: React.ReactNode;
}

const STAGES: StageInfo[] = [
  {
    key: "preprocessing",
    label: "Preprocessing",
    description: "Normalizing audio to 16kHz mono",
    icon: <AudioLines className="h-4 w-4" />,
  },
  {
    key: "transcribing",
    label: "Transcribing",
    description: "Running ASR inference on GPU",
    icon: <AudioWaveform className="h-4 w-4" />,
  },
  {
    key: "formatting",
    label: "Formatting",
    description: "Generating output files",
    icon: <FileText className="h-4 w-4" />,
  },
];

// Order map for comparing which stage comes first
const STAGE_ORDER: Record<string, number> = {
  pending: 0,
  preprocessing: 1,
  transcribing: 2,
  formatting: 3,
  completed: 4,
  failed: 99,
};

// ── Stage status logic ───────────────────────────────────

type StageStatus = "pending" | "active" | "done" | "failed";

function getStageStatus(
  stageKey: JobStatus,
  currentStage: JobStatus | null,
): StageStatus {
  if (!currentStage) return "pending";

  const stageIdx = STAGE_ORDER[stageKey] ?? 0;
  const currentIdx = STAGE_ORDER[currentStage] ?? 0;

  if (currentStage === "failed") {
    // Mark the stage where failure occurred as failed, earlier ones as done
    // We don't know exactly which stage failed, so mark all up to current as done
    // and the rest as pending. The error message tells the user what went wrong.
    return stageIdx <= currentIdx ? "done" : "pending";
  }

  if (stageIdx < currentIdx) return "done";
  if (stageIdx === currentIdx) return "active";
  return "pending";
}

// ── Props ────────────────────────────────────────────────

interface ProcessingViewProps {
  ws: WSState;
  filename: string;
}

// ── Component ────────────────────────────────────────────

export function ProcessingView({ ws, filename }: ProcessingViewProps) {
  return (
    <div className="w-full max-w-lg mx-auto flex flex-col items-center gap-8">
      {/* Header */}
      <div className="text-center">
        <p className="text-sm text-muted-foreground mb-1">{filename}</p>
        <h2 className="text-xl font-medium">Processing your audio</h2>
      </div>

      {/* Stage list */}
      <Card className="w-full p-1">
        <div className="flex flex-col">
          {STAGES.map((stage, idx) => {
            const status = getStageStatus(stage.key, ws.stage);
            const isActive = status === "active";
            const isDone = status === "done";
            const progressValue = isActive ? ws.progress * 100 : isDone ? 100 : 0;

            return (
              <div key={stage.key}>
                <div
                  className={`
                    flex items-center gap-3 px-4 py-3 rounded-lg transition-colors
                    ${isActive ? "bg-primary/5" : ""}
                  `}
                >
                  {/* Status icon */}
                  <div
                    className={`
                      h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0
                      ${isDone ? "bg-primary/10 text-primary" : ""}
                      ${isActive ? "bg-primary/10 text-primary" : ""}
                      ${status === "pending" ? "bg-muted text-muted-foreground" : ""}
                      ${status === "failed" ? "bg-destructive/10 text-destructive" : ""}
                    `}
                  >
                    {isDone && <Check className="h-4 w-4" />}
                    {isActive && <Loader2 className="h-4 w-4 animate-spin" />}
                    {status === "pending" && stage.icon}
                    {status === "failed" && <AlertCircle className="h-4 w-4" />}
                  </div>

                  {/* Label + description */}
                  <div className="flex-1 min-w-0">
                    <p
                      className={`
                        text-sm font-medium
                        ${isDone ? "text-muted-foreground" : ""}
                        ${isActive ? "text-foreground" : ""}
                        ${status === "pending" ? "text-muted-foreground/50" : ""}
                      `}
                    >
                      {stage.label}
                    </p>

                    {/* Active stage: show live message or description */}
                    {isActive && (
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">
                        {ws.message || stage.description}
                      </p>
                    )}
                  </div>

                  {/* Progress percentage for active stage */}
                  {isActive && (
                    <span className="text-xs font-mono text-muted-foreground flex-shrink-0">
                      {Math.round(ws.progress * 100)}%
                    </span>
                  )}

                  {/* Checkmark text for done */}
                  {isDone && (
                    <span className="text-xs text-muted-foreground flex-shrink-0">Done</span>
                  )}
                </div>

                {/* Progress bar for active stage */}
                {isActive && (
                  <div className="px-4 pb-3">
                    <Progress value={progressValue} className="h-1.5" />
                  </div>
                )}

                {/* Divider between stages */}
                {idx < STAGES.length - 1 && (
                  <div className="mx-4 h-px bg-border" />
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Error display */}
      {ws.error && (
        <div className="w-full px-4 py-3 rounded-lg bg-destructive/10 text-destructive text-sm flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-medium">Transcription failed</p>
            <p className="mt-0.5 opacity-80">{ws.error}</p>
          </div>
        </div>
      )}

      {/* Connection status indicator */}
      {ws.status === "connecting" && (
        <p className="text-xs text-muted-foreground animate-pulse">
          Connecting to server...
        </p>
      )}
    </div>
  );
}