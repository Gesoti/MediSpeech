import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, ChevronRight, PawPrint, X, Loader2 } from "lucide-react";
import type { Case, CaseCreate } from "@/types";
import { casesApi } from "@/api/client";
import { CaseForm } from "@/components/CaseForm";

export function CasesPage() {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    casesApi
      .list()
      .then(setCases)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async (data: CaseCreate) => {
    setCreating(true);
    setError(null);
    try {
      const newCase = await casesApi.create(data);
      setCases((prev) => [newCase, ...prev]);
      setShowForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create case");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Cases</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage veterinary imaging cases</p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus size={16} />
          New Case
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">New Case</h2>
            <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600">
              <X size={18} />
            </button>
          </div>
          <CaseForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} loading={creating} />
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 size={28} className="animate-spin text-slate-400" />
        </div>
      ) : cases.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <PawPrint size={40} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">No cases yet. Create your first one.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {cases.map((c) => (
            <Link
              key={c.id}
              to={`/cases/${c.id}`}
              className="bg-white rounded-xl border border-slate-200 px-5 py-4 flex items-center justify-between hover:border-primary-300 hover:shadow-sm transition-all group"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center">
                  <PawPrint size={18} className="text-primary-600" />
                </div>
                <div>
                  <p className="font-medium text-slate-800 capitalize">
                    {c.pet_species} — {c.pet_breed}
                  </p>
                  <p className="text-sm text-slate-500 uppercase tracking-wide">
                    {c.study_type}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-400">
                  {new Date(c.created_at).toLocaleDateString()}
                </span>
                <ChevronRight
                  size={16}
                  className="text-slate-400 group-hover:text-primary-500 transition-colors"
                />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
