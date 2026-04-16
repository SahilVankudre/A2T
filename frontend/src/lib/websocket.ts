/**
 * WebSocket hook — connects to the backend for live pipeline progress.
 *
 * Usage:
 *   const { stage, progress, message, job, error, status } = useWebSocket(jobId);
 *
 * Connects when jobId is provided, disconnects on unmount or when jobId
 * changes to null. Parses all three message types (progress, completed, error).
 *
 * Note: WebSocket connects directly to port 8000 (not through Next.js proxy,
 * since Next.js rewrites don't support WebSocket upgrade).
 *
 * Depends on:  types.ts (F03)
 * Depended by: processing-view.tsx (F07), page.tsx (F09)
 */

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  JobStatus,
  JobResponse,
  WSMessage,
} from "./types";

// ── Connection status ────────────────────────────────────

export type WSStatus = "disconnected" | "connecting" | "connected" | "error";

// ── Hook return type ─────────────────────────────────────

export interface WSState {
  /** Current pipeline stage (from last progress message) */
  stage: JobStatus | null;
  /** Progress within current stage: 0.0 - 1.0 */
  progress: number;
  /** Human-readable status message */
  message: string;
  /** Completed job data (set when pipeline finishes) */
  job: JobResponse | null;
  /** Error message (set when pipeline fails) */
  error: string | null;
  /** WebSocket connection status */
  status: WSStatus;
}

// ── Build WebSocket URL ──────────────────────────────────


function getWsUrl(jobId: string): string {
  if (typeof window === "undefined") return "";

  const hostname = window.location.hostname;

  // If accessed via ngrok or any non-localhost domain,
  // disable WebSocket (polling fallback handles completion)
  if (hostname !== "localhost" && hostname !== "127.0.0.1") {
    return "";
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${hostname}:8000/ws/${jobId}`;
}


// ── Hook ─────────────────────────────────────────────────

export function useWebSocket(jobId: string | null): WSState {
  const [state, setState] = useState<WSState>({
    stage: null,
    progress: 0,
    message: "",
    job: null,
    error: null,
    status: "disconnected",
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanup = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId) {
      cleanup();
      setState((s) => ({ ...s, status: "disconnected" }));
      return;
    }

    const url = getWsUrl(jobId);
    if (!url) return;

    let isCancelled = false;

    function connect() {
      if (isCancelled) return;

      setState((s) => ({ ...s, status: "connecting" }));

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isCancelled) return;
        setState((s) => ({ ...s, status: "connected" }));
      };

      ws.onmessage = (event) => {
        if (isCancelled) return;

        let msg: WSMessage;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return; // Ignore malformed messages
        }

        switch (msg.type) {
          case "progress":
            setState((s) => ({
              ...s,
              stage: msg.stage,
              progress: msg.progress,
              message: msg.message,
            }));
            break;

          case "completed":
            setState((s) => ({
              ...s,
              stage: "completed",
              progress: 1,
              message: "Transcription complete",
              job: msg.job,
              status: "disconnected",
            }));
            // Pipeline done — close connection cleanly
            ws.close();
            break;

          case "error":
            setState((s) => ({
              ...s,
              stage: "failed",
              error: msg.error,
              message: msg.error,
              status: "disconnected",
            }));
            ws.close();
            break;
        }
      };

      ws.onerror = () => {
        if (isCancelled) return;
        setState((s) => ({ ...s, status: "error" }));
      };

      ws.onclose = () => {
        if (isCancelled) return;
        wsRef.current = null;

        // Reconnect if we didn't close intentionally (not completed/failed)
        setState((s) => {
          if (s.stage === "completed" || s.stage === "failed") {
            return { ...s, status: "disconnected" };
          }
          // Connection dropped mid-pipeline — try reconnecting
          reconnectTimerRef.current = setTimeout(connect, 2000);
          return { ...s, status: "connecting" };
        });
      };
    }

    connect();

    return () => {
      isCancelled = true;
      cleanup();
    };
  }, [jobId, cleanup]);

  return state;
}

// ── Helper: reset state for new transcription ────────────

export function initialWSState(): WSState {
  return {
    stage: null,
    progress: 0,
    message: "",
    job: null,
    error: null,
    status: "disconnected",
  };
}