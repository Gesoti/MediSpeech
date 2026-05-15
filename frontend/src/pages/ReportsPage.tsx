import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, FileText, ChevronRight } from "lucide-react";
import type { Report } from "@/types";
import { reportsApi } from "@/api/client";

export function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .list()
      .then(setReports)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
        <p className="text-sm text-slate-500 mt-0.5">AI-generated clinical reports</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 size={28} className="animate-spin text-slate-400" />
        </div>
      ) : reports.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <FileText size={40} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">No reports yet. Generate one from a case.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {reports.map((r) => (
            <Link
              key={r.id}
              to={`/cases/${r.case_id}`}
              className="bg-white rounded-xl border border-slate-200 px-5 py-4 flex items-center justify-between hover:border-primary-300 hover:shadow-sm transition-all group"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center">
                  <FileText size={18} className="text-slate-500" />
                </div>
                <div>
                  <p className="font-medium text-slate-800 line-clamp-1">
                    {r.findings?.slice(0, 60) ?? "No findings"}…
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        r.status === "final"
                          ? "bg-green-100 text-green-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {r.status}
                    </span>
                    <span className="text-xs text-slate-400">
                      {new Date(r.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </div>
              <ChevronRight
                size={16}
                className="text-slate-400 group-hover:text-primary-500 transition-colors"
              />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
