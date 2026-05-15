import { useState } from "react";
import type { CaseCreate } from "@/types";

interface CaseFormProps {
  onSubmit: (data: CaseCreate) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

const SPECIES = ["dog", "cat", "rabbit", "bird", "horse", "other"];
const STUDY_TYPES = ["x-ray", "ultrasound", "MRI", "CT scan", "other"];

export function CaseForm({ onSubmit, onCancel, loading }: CaseFormProps) {
  const [form, setForm] = useState<CaseCreate>({
    pet_species: "",
    pet_breed: "",
    study_type: "",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(form);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">Species</label>
        <select
          required
          value={form.pet_species}
          onChange={(e) => setForm((f) => ({ ...f, pet_species: e.target.value }))}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">Select species…</option>
          {SPECIES.map((s) => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">Breed</label>
        <input
          required
          type="text"
          placeholder="e.g. Labrador Retriever"
          value={form.pet_breed}
          onChange={(e) => setForm((f) => ({ ...f, pet_breed: e.target.value }))}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">Study Type</label>
        <select
          required
          value={form.study_type}
          onChange={(e) => setForm((f) => ({ ...f, study_type: e.target.value }))}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">Select study type…</option>
          {STUDY_TYPES.map((t) => (
            <option key={t} value={t}>{t.toUpperCase()}</option>
          ))}
        </select>
      </div>
      <div className="flex gap-3 justify-end pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 rounded-lg transition-colors"
        >
          {loading ? "Creating…" : "Create Case"}
        </button>
      </div>
    </form>
  );
}
