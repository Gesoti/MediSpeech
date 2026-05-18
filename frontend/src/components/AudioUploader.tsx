import { useState, useRef, useCallback } from "react";
import { Upload, Mic, Square, Pause, Play, Loader2, Check, Edit2, Radio } from "lucide-react";
import type { Transcription } from "@/types";
import { audioApi, transcriptionsApi } from "@/api/client";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useApiError } from "@/hooks/useApiError";

interface AudioUploaderProps {
  caseId: string;
  onTranscribed: (t: Transcription) => void;
}

type RecordState = "idle" | "recording" | "paused" | "uploading" | "editing";

export function AudioUploader({ caseId, onTranscribed }: AudioUploaderProps) {
  const [recordState, setRecordState] = useState<RecordState>("idle");
  const { error, setError, clearError } = useApiError();
  const [dragOver, setDragOver] = useState(false);
  const [editableText, setEditableText] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [pendingTranscription, setPendingTranscription] = useState<Transcription | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadAndAppend = useCallback(
    async (file: File, existingText: string) => {
      setRecordState("uploading");
      setStreamingText("");
      clearError();
      try {
        let accumulated = "";
        const result = await audioApi.uploadStream(caseId, file, (segmentText) => {
          accumulated = accumulated
            ? `${accumulated} ${segmentText}`
            : segmentText;
          setStreamingText(accumulated);
        });

        const combined = existingText
          ? `${existingText.trimEnd()} ${result.raw_text.trimStart()}`
          : result.raw_text;

        const merged: Transcription = { ...result, raw_text: combined };
        setEditableText(combined);
        setPendingTranscription(merged);
        setStreamingText("");
        setRecordState("editing");
      } catch (e) {
        setError(e);
        setStreamingText("");
        setRecordState(existingText ? "editing" : "idle");
      }
    },
    [caseId],
  );

  const startRecording = async () => {
    clearError();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        void uploadAndAppend(
          new File([blob], "recording.webm", { type: "audio/webm" }),
          editableText,
        );
      };
      recorder.start();
      mediaRef.current = recorder;
      setRecordState("recording");
    } catch {
      setError(new Error("Microphone access denied"));
    }
  };

  const pauseRecording = () => {
    // Stop the current recording segment — onstop will upload it
    mediaRef.current?.stop();
    mediaRef.current = null;
    // recordState transitions to "uploading" then "editing" via uploadAndAppend
  };

  const stopAndUpload = () => {
    mediaRef.current?.stop();
    mediaRef.current = null;
  };

  const confirmEdits = async () => {
    if (!pendingTranscription) return;
    setSavingEdit(true);
    try {
      // Persist the user-edited text back to the DB
      const updated = await transcriptionsApi.update(pendingTranscription.id, editableText);
      onTranscribed(updated);
      // Reset
      setRecordState("idle");
      setEditableText("");
      setPendingTranscription(null);
    } catch (e) {
      setError(e);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void uploadAndAppend(file, editableText);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void uploadAndAppend(file, editableText);
    e.target.value = "";
  };

  const isUploading = recordState === "uploading";
  const isRecording = recordState === "recording";
  const isEditing = recordState === "editing";

  return (
    <div className="space-y-3">
      {/* Drop zone — hide during active recording */}
      {!isRecording && (
        <>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleFileDrop}
            onClick={() => !isUploading && fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
              dragOver
                ? "border-primary-400 bg-primary-50"
                : "border-slate-300 hover:border-primary-400 hover:bg-primary-50"
            } ${isUploading ? "pointer-events-none opacity-60" : ""}`}
          >
            {isUploading ? (
              <div className="flex flex-col items-start gap-2 w-full text-left">
                <div className="flex items-center gap-2 text-slate-500">
                  <Radio size={14} className="animate-pulse text-primary-500" />
                  <span className="text-xs font-medium text-primary-600 uppercase tracking-wide">
                    Transcribing…
                  </span>
                </div>
                {streamingText ? (
                  <p className="text-sm text-slate-700 leading-relaxed w-full">
                    {streamingText}
                    <span className="inline-block w-0.5 h-4 ml-0.5 bg-primary-500 align-text-bottom animate-pulse" />
                  </p>
                ) : (
                  <div className="flex items-center gap-2 text-slate-400">
                    <Loader2 size={14} className="animate-spin" />
                    <span className="text-xs">Waiting for first segment…</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-slate-500">
                <Upload size={24} />
                <span className="text-sm">
                  {isEditing ? "Drop another audio file to append" : "Drop audio file or click to browse"}
                </span>
                <span className="text-xs text-slate-400">WAV, MP3, WebM, OGG supported</span>
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={handleFileSelect}
          />
        </>
      )}

      {/* Transcription edit area */}
      {isEditing && (
        <div className="rounded-xl border border-primary-200 bg-primary-50 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Edit2 size={14} className="text-primary-600" />
            <p className="text-xs font-semibold text-primary-700 uppercase tracking-wide">
              Review & edit transcription
            </p>
          </div>
          <textarea
            rows={5}
            value={editableText}
            onChange={(e) => setEditableText(e.target.value)}
            className="w-full border border-primary-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none bg-white"
            placeholder="Transcribed text…"
          />
          <div className="flex gap-2">
            <button
              onClick={startRecording}
              disabled={savingEdit}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors disabled:opacity-50"
            >
              <Mic size={14} />
              Record more
            </button>
            <button
              onClick={confirmEdits}
              disabled={savingEdit || !editableText.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {savingEdit ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Check size={14} />
              )}
              {savingEdit ? "Saving…" : "Confirm transcription"}
            </button>
          </div>
        </div>
      )}

      {/* Record controls */}
      {!isEditing && (
        <>
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-slate-200" />
            <span className="text-xs text-slate-400">or record directly</span>
            <div className="flex-1 h-px bg-slate-200" />
          </div>

          {isRecording ? (
            <div className="flex gap-2">
              <button
                onClick={pauseRecording}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium bg-amber-100 hover:bg-amber-200 text-amber-700 transition-colors"
              >
                <Pause size={15} />
                Pause & Edit
              </button>
              <button
                onClick={stopAndUpload}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium bg-red-500 hover:bg-red-600 text-white transition-colors"
              >
                <Square size={15} />
                Stop Recording
              </button>
            </div>
          ) : (
            <button
              onClick={startRecording}
              disabled={isUploading}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors disabled:opacity-50"
            >
              <Play size={15} />
              {isUploading ? "Processing…" : "Start Recording"}
            </button>
          )}
        </>
      )}

      {error && <ErrorBanner message={error} onDismiss={clearError} />}
    </div>
  );
}
