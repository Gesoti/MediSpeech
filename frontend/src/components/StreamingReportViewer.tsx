import { useEffect, useRef, useState } from "react";
import { Loader2, CheckCircle, AlertCircle, Save } from "lucide-react";
import type { Report, ReportSection, StreamEvent } from "@/types";
import { reportsApi } from "@/api/client";

interface StreamingReportViewerProps {
  transcriptionId: string;
  studyType: string;
  onComplete: (report: Report) => void;
  onCancel: () => void;
}

const SECTION_LABELS: Record<ReportSection, string> = {
  clinical_history: "Clinical History",
  findings: "Radiological Findings",
  impressions: "Clinical Impression",
  recommendations: "Recommendations",
};

const SECTION_ORDER: ReportSection[] = [
  "clinical_history",
  "findings",
  "impressions",
  "recommendations",
];

type SectionStatus = "pending" | "streaming" | "done";

interface SectionState {
  status: SectionStatus;
  text: string;
}

export function StreamingReportViewer({
  transcriptionId,
  studyType,
  onComplete,
  onCancel,
}: StreamingReportViewerProps) {
  const [sections, setSections] = useState<Record<ReportSection, SectionState>>(
    () =>
      Object.fromEntries(
        SECTION_ORDER.map((k) => [k, { status: "pending", text: "" }]),
      ) as Record<ReportSection, SectionState>,
  );
  const [streamDone, setStreamDone] = useState(false);
  const [saving, setSaving] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const completedData = useRef<Partial<Record<ReportSection, string>>>({});

  useEffect(() => {
    const cleanup = reportsApi.streamGenerate(
      transcriptionId,
      (event: StreamEvent) => {
        if (event.status === "complete") {
          // Store final texts from the completion event
          SECTION_ORDER.forEach((sec) => {
            const val = event[sec];
            if (val) completedData.current[sec] = val;
          });
          setSections((prev) => {
            const next = { ...prev };
            SECTION_ORDER.forEach((sec) => {
              if (event[sec]) {
                next[sec] = { status: "done", text: event[sec] as string };
              }
            });
            return next;
          });
          setStreamDone(true);
          return;
        }

        if (!event.section) return;
        const sec = event.section;

        if (event.status === "start") {
          setSections((prev) => ({
            ...prev,
            [sec]: { status: "streaming", text: "" },
          }));
        } else if (event.token) {
          setSections((prev) => ({
            ...prev,
            [sec]: {
              status: "streaming",
              text: prev[sec].text + event.token,
            },
          }));
        } else if (event.status === "done" && event.text) {
          completedData.current[sec] = event.text;
          setSections((prev) => ({
            ...prev,
            [sec]: { status: "done", text: event.text as string },
          }));
        }
      },
      () => setStreamDone(true),
      (err) => setStreamError(err),
    );

    return cleanup;
  }, [transcriptionId]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const report = await reportsApi.saveStreamed(transcriptionId, {
        clinical_history: completedData.current.clinical_history ?? null,
        findings: completedData.current.findings ?? null,
        impressions: completedData.current.impressions ?? null,
        recommendations: completedData.current.recommendations ?? null,
      });
      onComplete(report);
    } catch (e) {
      setStreamError(e instanceof Error ? e.message : "Failed to save report");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-slate-800">Generating Clinical Report</h3>
          <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-blue-100 text-blue-700 uppercase">
            {studyType}
          </span>
        </div>
        {!streamDone && !streamError && (
          <div className="flex items-center gap-1.5 text-sm text-slate-400">
            <Loader2 size={14} className="animate-spin" />
            Streaming…
          </div>
        )}
        {streamDone && !saving && (
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              className="px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100 rounded-lg transition-colors"
            >
              Discard
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              <Save size={14} />
              Save Report
            </button>
          </div>
        )}
      </div>

      {streamError && (
        <div className="px-5 py-4 flex items-center gap-2 text-red-600 bg-red-50">
          <AlertCircle size={16} />
          <span className="text-sm">{streamError}</span>
        </div>
      )}

      {/* Sections */}
      <div className="divide-y divide-slate-50">
        {SECTION_ORDER.map((sec) => {
          const { status, text } = sections[sec];
          return (
            <div key={sec} className="px-5 py-4">
              <div className="flex items-center gap-2 mb-2">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  {SECTION_LABELS[sec]}
                </p>
                {status === "streaming" && (
                  <Loader2 size={12} className="animate-spin text-primary-500" />
                )}
                {status === "done" && (
                  <CheckCircle size={12} className="text-green-500" />
                )}
              </div>
              {status === "pending" ? (
                <div className="h-4 w-32 rounded bg-slate-100 animate-pulse" />
              ) : (
                <p className="text-sm text-slate-700 whitespace-pre-wrap">
                  {text}
                  {status === "streaming" && (
                    <span className="inline-block w-1 h-4 ml-0.5 bg-primary-500 animate-pulse align-middle" />
                  )}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {saving && (
        <div className="px-5 py-3 border-t border-slate-100 flex items-center gap-2 text-slate-500">
          <Loader2 size={14} className="animate-spin" />
          <span className="text-sm">Saving report…</span>
        </div>
      )}
    </div>
  );
}
