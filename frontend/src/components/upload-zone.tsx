/**
 * Upload zone — drag-and-drop audio upload with "Try sample" button.
 *
 * Passes both the API response and original filename back to parent.
 *
 * Depends on:  types.ts (F03), api.ts (F04)
 * Depended by: page.tsx (F09)
 */

"use client";

import { useState, useRef, useCallback } from "react";
import { Upload, Loader2, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { uploadAudio, uploadSample, ApiError } from "@/lib/api";
import type { JobCreateResponse } from "@/lib/types";

const ACCEPTED_EXTENSIONS = [
  ".wav", ".mp3", ".flac", ".m4a", ".ogg",
  ".opus", ".wma", ".aac", ".webm", ".mp4",
];

const ACCEPT_STRING = "audio/*,.mp4";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface UploadZoneProps {
  onUploadComplete: (response: JobCreateResponse, filename: string) => void;
}

export function UploadZone({ onUploadComplete }: UploadZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = useCallback((file: File): string | null => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      return `Unsupported format: ${ext}. Use ${ACCEPTED_EXTENSIONS.join(", ")}`;
    }
    if (file.size > 500 * 1024 * 1024) {
      return `File too large: ${formatFileSize(file.size)} (max 500 MB)`;
    }
    if (file.size === 0) return "File is empty";
    return null;
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    const validationError = validateFile(file);
    if (validationError) { setError(validationError); return; }

    setSelectedFile(file);
    setError(null);
    setIsUploading(true);

    try {
      const response = await uploadAudio(file);
      onUploadComplete(response, file.name);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Upload failed. Is the backend running on port 8000?");
      }
      setIsUploading(false);
    }
  }, [validateFile, onUploadComplete]);

  const handleSampleUpload = useCallback(async () => {
    setError(null);
    setIsUploading(true);
    setSelectedFile(null);

    try {
      const response = await uploadSample();
      onUploadComplete(response, "sample.wav");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load sample audio. Check that /sample.wav exists in public/.");
      }
      setIsUploading(false);
    }
  }, [onUploadComplete]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }, [handleUpload]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    e.target.value = "";
  }, [handleUpload]);

  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-xl mx-auto">
      <Card
        className={`
          w-full p-10 flex flex-col items-center gap-4 cursor-pointer
          border-2 border-dashed transition-all duration-200
          ${isDragOver
            ? "border-primary bg-primary/5 scale-[1.01]"
            : "border-muted-foreground/20 hover:border-muted-foreground/40 hover:bg-muted/30"
          }
          ${isUploading ? "pointer-events-none opacity-60" : ""}
        `}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
      >
        <input ref={fileInputRef} type="file" accept={ACCEPT_STRING} onChange={handleFileSelect} className="hidden" />

        {isUploading ? (
          <>
            <Loader2 className="h-10 w-10 text-primary animate-spin" />
            <div className="text-center">
              <p className="font-medium">Uploading{selectedFile ? `: ${selectedFile.name}` : " sample audio"}...</p>
              {selectedFile && (
                <p className="text-sm text-muted-foreground mt-1">{formatFileSize(selectedFile.size)}</p>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
              <Upload className="h-6 w-6 text-muted-foreground" />
            </div>
            <div className="text-center">
              <p className="font-medium">Drop an audio file here, or click to browse</p>
              <p className="text-sm text-muted-foreground mt-1">
                WAV, MP3, FLAC, M4A, OGG, OPUS — up to 500 MB
              </p>
            </div>
          </>
        )}
      </Card>

      {error && (
        <div className="w-full px-4 py-3 rounded-lg bg-destructive/10 text-destructive text-sm">
          {error}
        </div>
      )}

      <div className="flex items-center gap-3">
        <div className="h-px w-12 bg-border" />
        <span className="text-xs text-muted-foreground uppercase tracking-wider">or</span>
        <div className="h-px w-12 bg-border" />
      </div>

      <Button variant="outline" size="lg" onClick={handleSampleUpload} disabled={isUploading} className="gap-2">
        <Mic className="h-4 w-4" />
        Try with sample audio
      </Button>
    </div>
  );
}