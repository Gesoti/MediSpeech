import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  Loader2,
  Mic,
  FileText,
  ChevronDown,
  ChevronUp,
  PawPrint,
  Wand2,
  Zap,
  Pencil,
  Check,
  X,
} from "lucide-react";
import type { Case, Transcription, Report } from "@/types";
import { casesApi, audioApi, reportsApi, transcriptionsApi } from "@/api/client";
import { AudioUploader } from "@/components/AudioUploader";
import { ReportEditor } from "@/components/ReportEditor";
import { StreamingReportViewer } from "@/components/StreamingReportViewer";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useApiError } from "@/hooks/useApiError";

type ReportMode = "none" | "streaming" | "done";

export function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { error: reportError, setError: setReportError, clearError: clearReportError } = useApiError();
  const [expandedTx, setExpandedTx] = useState<string | null>(null);
  const [reportMode, setReportMode] = useState<ReportMode>("none");
  const [streamingTxId, setStreamingTxId] = useState<string | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [editingTxId, setEditingTxId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [savingTx, setSavingTx] = useState(false);

  useEffect(() => {
    if (!id) return;

    const fetchAll = async () => {
      try {
        const [c, txs] = await Promise.all([
          casesApi.get(id),
          audioApi.listTranscriptions(id),
        ]);
        setCaseData(c);
        setTranscriptions(txs);

        try {
          const r = await reportsApi.getByCase(id);
          setReport(r);
          setReportMode("done");
        } catch {
          // no report yet
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load case");
      } finally {
        setLoading(false);
      }
    };

    void fetchAll();
  }, [id]);

  const handleTranscribed = (t: Transcription) => {
    setTranscriptions((prev) => [t, ...prev]);
    setExpandedTx(t.id);
  };

  /** Streaming path — opens SSE and shows StreamingReportViewer */
  const generateReportStream = (transcriptionId: string) => {
    setStreamingTxId(transcriptionId);
    setReportMode("streaming");
    clearReportError();
  };

  const startEditing = (t: Transcription) => {
    setEditingTxId(t.id);
    setEditDraft(t.raw_text);
  };

  const saveEdit = async (id: string) => {
    setSavingTx(true);
    try {
      const updated = await transcriptionsApi.update(id, editDraft);
      setTranscriptions((prev) => prev.map((t) => (t.id === id ? updated : t)));
      setEditingTxId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSavingTx(false);
    }
  };

  /** Blocking fallback (kept for reliability) */
  const generateReportBlocking = async (transcriptionId: string) => {
    setGeneratingReport(true);
    clearReportError();
    try {
      const r = await reportsApi.create({ transcription_id: transcriptionId });
      setReport(r);
      setReportMode("done");
    } catch (e) {
      setReportError(e);
    } finally {
      setGeneratingReport(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 size={28} className="animate-spin text-slate-400" />
      </div>
    );
  }

  if (error && !caseData) {
    return <div className="text-center py-24 text-red-600 text-sm">{error}</div>;
  }

  if (!caseData) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link
          to="/"
          className="mt-1 p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <ArrowLeft size={18} />
        </Link>
        <div>
          <div className="flex items-center gap-2">
            <PawPrint size={20} className="text-primary-500" />
            <h1 className="text-2xl font-bold text-slate-900 capitalize">
              {caseData.pet_species} — {caseData.pet_breed}
            </h1>
          </div>
          <p className="text-sm text-slate-500 mt-0.5 uppercase tracking-wide">
            {caseData.study_type} &middot; {new Date(caseData.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>

      {error && (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Audio upload */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Mic size={18} className="text-primary-500" />
            <h2 className="font-semibold text-slate-800">Record / Upload Audio</h2>
          </div>
          <AudioUploader caseId={caseData.id} onTranscribed={handleTranscribed} />
        </div>

        {/* Transcriptions */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-2 mb-4">
            <FileText size={18} className="text-primary-500" />
            <h2 className="font-semibold text-slate-800">Transcriptions</h2>
            <span className="ml-auto text-xs text-slate-400">{transcriptions.length} total</span>
          </div>
          {transcriptions.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">
              No transcriptions yet. Upload an audio file to begin.
            </p>
          ) : (
            <div className="space-y-2">
              {transcriptions.map((t) => (
                <div key={t.id} className="border border-slate-200 rounded-lg overflow-hidden">
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => setExpandedTx(expandedTx === t.id ? null : t.id)}
                    onKeyDown={(e) =>
                      e.key === "Enter" &&
                      setExpandedTx(expandedTx === t.id ? null : t.id)
                    }
                    className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50 transition-colors cursor-pointer"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-700">
                        {new Date(t.created_at).toLocaleString()}
                      </p>
                      <p className="text-xs text-slate-400">
                        {t.model_used}
                        {t.confidence != null &&
                          ` · ${(t.confidence * 100).toFixed(0)}% confidence`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {reportMode === "none" && (
                        <>
                          {/* Streaming generate (preferred) */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              generateReportStream(t.id);
                            }}
                            className="flex items-center gap-1 px-2 py-1 text-xs font-medium bg-primary-100 text-primary-700 hover:bg-primary-200 rounded transition-colors"
                            title="Generate report with live streaming"
                          >
                            <Zap size={11} />
                            Stream Report
                          </button>
                          {/* Blocking fallback */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void generateReportBlocking(t.id);
                            }}
                            disabled={generatingReport}
                            className="flex items-center gap-1 px-2 py-1 text-xs font-medium bg-slate-100 text-slate-600 hover:bg-slate-200 rounded disabled:opacity-50 transition-colors"
                            title="Generate report (blocking)"
                          >
                            <Wand2 size={11} />
                            {generatingReport ? "Generating…" : "Generate"}
                          </button>
                        </>
                      )}
                      {expandedTx === t.id ? (
                        <ChevronUp size={15} className="text-slate-400" />
                      ) : (
                        <ChevronDown size={15} className="text-slate-400" />
                      )}
                    </div>
                  </div>
                  {expandedTx === t.id && (
                    <div className="px-4 py-3 bg-slate-50 border-t border-slate-200">
                      {editingTxId === t.id ? (
                        <div className="space-y-2">
                          <textarea
                            className="w-full text-sm text-slate-700 bg-white border border-primary-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-400 resize-y min-h-[80px]"
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                            autoFocus
                          />
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => void saveEdit(t.id)}
                              disabled={savingTx}
                              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
                            >
                              {savingTx ? (
                                <Loader2 size={11} className="animate-spin" />
                              ) : (
                                <Check size={11} />
                              )}
                              Save
                            </button>
                            <button
                              onClick={() => setEditingTxId(null)}
                              disabled={savingTx}
                              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-slate-500 hover:bg-slate-200 rounded-lg disabled:opacity-50 transition-colors"
                            >
                              <X size={11} />
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="group relative">
                          <p className="text-sm text-slate-700 whitespace-pre-wrap pr-8">{t.raw_text}</p>
                          <button
                            onClick={() => startEditing(t)}
                            className="absolute top-0 right-0 p-1 rounded text-slate-300 hover:text-slate-600 hover:bg-slate-200 opacity-0 group-hover:opacity-100 transition-all"
                            title="Edit transcription"
                          >
                            <Pencil size={13} />
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Report generation error */}
      {reportError && (
        <ErrorBanner message={reportError} onDismiss={clearReportError} />
      )}

      {/* Streaming report generation */}
      {reportMode === "streaming" && streamingTxId && (
        <StreamingReportViewer
          transcriptionId={streamingTxId}
          studyType={caseData.study_type}
          onComplete={(r) => {
            setReport(r);
            setReportMode("done");
            setStreamingTxId(null);
          }}
          onCancel={() => {
            setReportMode("none");
            setStreamingTxId(null);
          }}
        />
      )}

      {/* Completed report editor */}
      {reportMode === "done" && report && (
        <ReportEditor report={report} onUpdate={setReport} />
      )}
    </div>
  );
}
