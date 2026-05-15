import type {
  Case,
  CaseCreate,
  CaseUpdate,
  Transcription,
  Report,
  ReportCreate,
  ReportUpdate,
  StreamedReportSave,
  StreamEvent,
} from "@/types";

const BASE = "/api";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// Cases
export const casesApi = {
  list: () => request<Case[]>("/cases"),
  get: (id: string) => request<Case>(`/cases/${id}`),
  create: (data: CaseCreate) =>
    request<Case>("/cases", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: CaseUpdate) =>
    request<Case>(`/cases/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    request<void>(`/cases/${id}`, { method: "DELETE" }),
};

// Audio upload (multipart)
export const audioApi = {
  upload: async (caseId: string, file: File): Promise<Transcription> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/audio/${caseId}/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<Transcription>;
  },
  listTranscriptions: (caseId: string) =>
    request<Transcription[]>(`/audio/${caseId}/transcriptions`),
  getTranscription: (transcriptionId: string) =>
    request<Transcription>(`/audio/${transcriptionId}`),
};

// Reports
export const reportsApi = {
  create: (data: ReportCreate) =>
    request<Report>("/reports", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getByCase: (caseId: string) => request<Report>(`/reports/${caseId}`),
  update: (reportId: string, data: ReportUpdate) =>
    request<Report>(`/reports/${reportId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  finalize: (reportId: string) =>
    request<Report>(`/reports/${reportId}/finalize`, { method: "POST" }),
  list: () => request<Report[]>("/reports"),

  /** Open an SSE stream for report generation. Returns an EventSource and a
   *  cleanup function. The caller provides callbacks for each event type. */
  streamGenerate: (
    transcriptionId: string,
    onEvent: (e: StreamEvent) => void,
    onDone: () => void,
    onError: (err: string) => void,
  ): (() => void) => {
    const es = new EventSource(`${BASE}/reports/stream/${transcriptionId}`);
    es.onmessage = (raw) => {
      try {
        const event = JSON.parse(raw.data as string) as StreamEvent;
        if (event.status === "complete") {
          onEvent(event);
          onDone();
          es.close();
        } else if (event.error) {
          onError(event.error);
          es.close();
        } else {
          onEvent(event);
        }
      } catch {
        // ignore parse errors from keep-alive pings
      }
    };
    es.onerror = () => {
      onError("Connection lost");
      es.close();
    };
    return () => es.close();
  },

  saveStreamed: (transcriptionId: string, data: StreamedReportSave) =>
    request<Report>(`/reports/stream/${transcriptionId}/save`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Transcriptions — update editable text after user correction
export const transcriptionsApi = {
  update: (transcriptionId: string, rawText: string) =>
    request<Transcription>(`/transcriptions/${transcriptionId}`, {
      method: "PATCH",
      body: JSON.stringify({ raw_text: rawText }),
    }),
};
