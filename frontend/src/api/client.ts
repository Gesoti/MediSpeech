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
const TOKEN_KEY = "ms_token";

function authHeader(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeader(), ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// Auth
export const authApi = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (name: string, email: string, password: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),
};

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
      headers: authHeader(),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<Transcription>;
  },

  /** Stream transcription segments as they are decoded.
   *  Calls onSegment for each arriving text chunk.
   *  Resolves with the final Transcription once the stream is complete. */
  uploadStream: async (
    caseId: string,
    file: File,
    onSegment: (text: string) => void,
  ): Promise<Transcription> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/audio/${caseId}/upload/stream`, {
      method: "POST",
      body: form,
      headers: authHeader(),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `HTTP ${res.status}`);
    }

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6);
        const event = JSON.parse(payload) as {
          type: "segment" | "done" | "error";
          text?: string;
          transcription_id?: string;
          audio_file_id?: string;
          confidence?: number | null;
          model?: string;
          raw_text?: string;
          detail?: string;
        };
        if (event.type === "error") throw new Error(event.detail ?? "Transcription failed");
        if (event.type === "segment" && event.text) onSegment(event.text);
        if (event.type === "done") {
          return {
            id: event.transcription_id!,
            audio_file_id: event.audio_file_id!,
            raw_text: event.raw_text!,
            confidence: event.confidence ?? null,
            model_used: event.model!,
            created_at: new Date().toISOString(),
          };
        }
      }
    }
    throw new Error("Stream ended without a done event");
  },
  /** Transcribe a short audio chunk for live preview — no DB record created. */
  previewTranscribe: async (file: File): Promise<string> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/audio/preview`, {
      method: "POST",
      body: form,
      headers: authHeader(),
    });
    if (!res.ok) return "";
    const data = await res.json() as { text: string };
    return data.text ?? "";
  },

  /** WebSocket URL for live recording — works through Vite proxy in dev and nginx in prod. */
  liveWsUrl: (caseId: string): string => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/api/audio/${caseId}/ws`;
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
