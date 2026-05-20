import { useState, useRef, useCallback, useEffect } from "react";
import { Upload, Mic, Square, Pause, Play, Loader2, Check, Edit2, Radio } from "lucide-react";
import type { Transcription } from "@/types";
import { audioApi, transcriptionsApi } from "@/api/client";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useApiError } from "@/hooks/useApiError";

const CHUNK_INTERVAL_MS = 3000;
const WORD_REVEAL_MS = 60;

/** Animates a target string word-by-word whenever it changes. */
function useWordReveal(target: string): string {
  const [revealed, setRevealed] = useState("");
  const revealedRef = useRef("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);

    if (!target) {
      revealedRef.current = "";
      setRevealed("");
      return;
    }

    // Only animate the words not yet shown; use ref to avoid stale closure.
    const prev = revealedRef.current.trimEnd();
    const alreadyShown = prev && target.startsWith(prev) ? prev : "";
    const remaining = alreadyShown ? target.slice(alreadyShown.length).trimStart() : target;
    const newWords = remaining.split(/\s+/).filter(Boolean);

    if (!newWords.length) {
      revealedRef.current = target;
      setRevealed(target);
      return;
    }

    let i = 0;
    const base = alreadyShown ? alreadyShown + " " : "";

    const tick = () => {
      i++;
      const next = base + newWords.slice(0, i).join(" ");
      revealedRef.current = next;
      setRevealed(next);
      if (i < newWords.length) {
        timerRef.current = setTimeout(tick, WORD_REVEAL_MS);
      }
    };
    timerRef.current = setTimeout(tick, WORD_REVEAL_MS);

    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [target]);

  return revealed;
}

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
  const [liveText, setLiveText] = useState("");
  const revealedLive = useWordReveal(liveText);
  const revealedStreaming = useWordReveal(streamingText);

  const mediaRef = useRef<MediaRecorder | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  // Track editableText in a ref so WS message handlers always see the current value.
  const editableTextRef = useRef(editableText);
  useEffect(() => { editableTextRef.current = editableText; }, [editableText]);

  // Close any open WebSocket when the component unmounts mid-recording.
  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

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
        setLiveText("");
        setRecordState("editing");
      } catch (e) {
        setError(e);
        setStreamingText("");
        setLiveText("");
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

      // Open WebSocket — stays open for the full recording session
      const ws = new WebSocket(audioApi.liveWsUrl(caseId));
      ws.binaryType = "blob";
      wsRef.current = ws;

      ws.onmessage = (e: MessageEvent<string>) => {
        const event = JSON.parse(e.data) as {
          type: "partial" | "final" | "error";
          text?: string;
          transcription_id?: string;
          audio_file_id?: string;
          confidence?: number | null;
          model?: string;
          detail?: string;
        };

        if (event.type === "partial" && event.text) {
          setLiveText(event.text);
        }

        if (event.type === "final") {
          const transcription: Transcription = {
            id: event.transcription_id!,
            audio_file_id: event.audio_file_id!,
            raw_text: event.text ?? "",
            confidence: event.confidence ?? null,
            model_used: event.model ?? "faster-whisper",
            created_at: new Date().toISOString(),
          };
          // Use ref to read current editableText — not the value captured at recording start.
          const base = editableTextRef.current;
          const combined = base
            ? `${base.trimEnd()} ${transcription.raw_text.trimStart()}`
            : transcription.raw_text;
          const merged: Transcription = { ...transcription, raw_text: combined };
          setEditableText(combined);
          setPendingTranscription(merged);
          setLiveText("");
          setRecordState("editing");
        }

        if (event.type === "error") {
          setError(new Error(event.detail ?? "Live transcription failed"));
          setLiveText("");
          setRecordState(editableTextRef.current ? "editing" : "idle");
        }
      };

      ws.onerror = () => {
        setError(new Error("WebSocket connection failed"));
        setLiveText("");
        setRecordState(editableTextRef.current ? "editing" : "idle");
      };

      recorder.ondataavailable = (e) => {
        if (!e.data.size) return;
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(e.data);
        }
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        // Signal end-of-recording; server does final transcription + DB save
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "end" }));
        }
        setRecordState("uploading");
      };

      recorder.start(CHUNK_INTERVAL_MS);
      mediaRef.current = recorder;
      setRecordState("recording");
    } catch {
      setError(new Error("Microphone access denied"));
    }
  };

  const pauseRecording = () => {
    mediaRef.current?.stop();
    mediaRef.current = null;
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
      setRecordState("idle");
      setEditableText("");
      setPendingTranscription(null);
      setLiveText("");
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
                {revealedStreaming || revealedLive ? (
                  <p className="text-sm text-slate-700 leading-relaxed w-full">
                    {revealedStreaming || revealedLive}
                    <span className="inline-block w-0.5 h-4 ml-0.5 bg-primary-500 align-text-bottom animate-pulse" />
                  </p>
                ) : (
                  <div className="flex items-center gap-2 text-slate-400">
                    <Loader2 size={14} className="animate-spin" />
                    <span className="text-xs">Processing…</span>
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
            <div className="space-y-3">
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

              {/* Live transcription preview */}
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 min-h-[80px]">
                <div className="flex items-center gap-1.5 mb-2">
                  <Mic size={12} className="text-red-500 animate-pulse" />
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                    Listening…
                  </span>
                </div>
                {revealedLive ? (
                  <p className="text-sm text-slate-700 leading-relaxed">
                    {revealedLive}
                    <span className="inline-block w-0.5 h-4 ml-0.5 bg-primary-500 align-text-bottom animate-pulse" />
                  </p>
                ) : (
                  <p className="text-sm text-slate-400 italic">
                    Speak — words will appear here…
                  </p>
                )}
              </div>
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
