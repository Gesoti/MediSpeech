import { useState } from "react";
import { CheckCircle, Edit2, Save, Lock } from "lucide-react";
import type { Report, ReportUpdate } from "@/types";
import { reportsApi } from "@/api/client";

interface ReportEditorProps {
  report: Report;
  onUpdate: (r: Report) => void;
}

const SECTIONS: { key: keyof ReportUpdate; label: string }[] = [
  { key: "findings", label: "Radiological Findings" },
  { key: "impressions", label: "Clinical Impression" },
  { key: "recommendations", label: "Recommendations" },
];

export function ReportEditor({ report, onUpdate }: ReportEditorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ReportUpdate>({
    findings: report.findings,
    impressions: report.impressions,
    recommendations: report.recommendations,
  });
  const [saving, setSaving] = useState(false);
  const [finalizing, setFinalizing] = useState(false);

  const isFinal = report.status === "final";

  const save = async () => {
    setSaving(true);
    try {
      const updated = await reportsApi.update(report.id, draft);
      onUpdate(updated);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const finalize = async () => {
    setFinalizing(true);
    try {
      const updated = await reportsApi.finalize(report.id);
      onUpdate(updated);
    } finally {
      setFinalizing(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-slate-800">Clinical Report</h3>
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              isFinal
                ? "bg-green-100 text-green-700"
                : "bg-amber-100 text-amber-700"
            }`}
          >
            {isFinal ? "Final" : "Draft"}
          </span>
        </div>
        {!isFinal && (
          <div className="flex gap-2">
            {editing ? (
              <button
                onClick={save}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
              >
                <Save size={14} />
                {saving ? "Saving…" : "Save"}
              </button>
            ) : (
              <button
                onClick={() => setEditing(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <Edit2 size={14} />
                Edit
              </button>
            )}
            <button
              onClick={finalize}
              disabled={finalizing || editing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              <CheckCircle size={14} />
              {finalizing ? "Finalizing…" : "Finalize"}
            </button>
          </div>
        )}
        {isFinal && (
          <div className="flex items-center gap-1 text-sm text-slate-400">
            <Lock size={14} />
            Read-only
          </div>
        )}
      </div>

      {report.clinical_history && (
        <div className="px-5 py-4 border-b border-slate-50 bg-slate-50">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Clinical History</p>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{report.clinical_history}</p>
        </div>
      )}

      <div className="divide-y divide-slate-50">
        {SECTIONS.map(({ key, label }) => (
          <div key={key} className="px-5 py-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{label}</p>
            {editing ? (
              <textarea
                rows={4}
                value={(draft[key] as string | null | undefined) ?? ""}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, [key]: e.target.value }))
                }
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
              />
            ) : (
              <p className="text-sm text-slate-700 whitespace-pre-wrap">
                {(report[key as keyof Report] as string | null) ?? (
                  <span className="text-slate-400 italic">Not generated</span>
                )}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
