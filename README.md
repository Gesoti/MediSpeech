# MediSpeech

Medical speech transcription and clinical reporting system for veterinary practices.

A veterinary radiologist speaks their observations into a microphone. MediSpeech captures the audio, transcribes it with OpenAI Whisper, and then runs a four-step clinical reasoning pipeline (via BioGPT) to produce a structured radiology report with Clinical History, Findings, Impressions, and Recommendations sections — all streamed to the browser in real time.

---

## Table of Contents

1. [Architecture overview](#1-architecture-overview)
2. [Component descriptions](#2-component-descriptions)
3. [Data model](#3-data-model)
4. [API reference](#4-api-reference)
5. [Running locally (development)](#5-running-locally-development)
6. [Running with Docker Compose](#6-running-with-docker-compose)
7. [Running tests](#7-running-tests)
8. [Kubernetes deployment](#8-kubernetes-deployment)
9. [Environment variables](#9-environment-variables)
10. [Observability (Langfuse)](#10-observability-langfuse)

---

## 1. Architecture overview

```
Browser (React + Vite)
        │
        │  REST + SSE (port 5173 in dev, proxied to 8000)
        ▼
┌─────────────────────────────┐
│   FastAPI API  (:8000)      │
│                             │
│  routes/cases.py            │  CRUD for veterinary cases
│  routes/audio.py            │  audio upload → Whisper → Transcription
│  routes/transcription.py    │  read/edit transcription text
│  routes/reports.py          │  LangGraph pipeline → Report (blocking + SSE)
│                             │
│  services/audio_service.py  │  wraps Whisper in a thread pool
│  services/llm_service.py    │  wraps BioGPT in a thread pool
│  services/langgraph_service.py │ 4-step clinical workflow
│                             │
│  utils/tracing.py           │  Langfuse observability (best-effort)
└──────────┬──────────────────┘
           │  asyncpg
           ▼
┌──────────────────┐     ┌────────────────────────┐
│  PostgreSQL :5432 │     │  Langfuse :3000         │
│  (medispeech DB) │     │  (trace dashboard)      │
└──────────────────┘     └────────────────────────┘
```

The `services/` directory at the repo root contains **standalone microservices** that mirror the in-process services above. They are designed for independent horizontal scaling and expose their own HTTP APIs:

```
services/
├── transcription/   Whisper microservice (:8001)
└── llm/             BioGPT microservice (:8002)
```

In the current default deployment the main FastAPI app calls Whisper and BioGPT **in-process** (via thread pools). Extracting them to the standalone microservices is a future scaling step.

---

## 2. Component descriptions

### FastAPI backend (`backend/`)

The primary application. All business logic, database access, and ML inference live here.

| File | Responsibility |
|------|----------------|
| `app/main.py` | Application factory: creates the FastAPI app, registers CORS, mounts routers, runs DB migrations on startup, flushes Langfuse on shutdown |
| `app/config.py` | Typed settings via `pydantic-settings`; reads from `.env` or environment |
| `app/db.py` | Async SQLAlchemy engine + `AsyncSession` factory + `get_db` FastAPI dependency |
| `app/routes/cases.py` | CRUD for `Case` records (POST, GET list, GET one, PATCH, DELETE) |
| `app/routes/audio.py` | Upload audio → Whisper transcription (stored in DB); list/get transcriptions by case |
| `app/routes/transcription.py` | Read and user-edit transcription text (`GET /api/transcriptions/{audio_file_id}`, `PATCH /api/transcriptions/{id}`) |
| `app/routes/reports.py` | Generate a clinical report (blocking `POST /api/reports` or streaming `POST /api/reports/stream/{transcription_id}`); save, update, finalize |
| `app/services/audio_service.py` | Wraps `openai-whisper`; loads model lazily; runs CPU-bound transcription in a `ThreadPoolExecutor` so the async event loop is never blocked |
| `app/services/llm_service.py` | Wraps `microsoft/BioGPT` via HuggingFace Transformers; same thread-pool pattern; also exposes `generate_stream` which yields word-by-word after a full generation pass |
| `app/services/langgraph_service.py` | The four-step clinical pipeline: extract history → generate findings → generate impressions → generate recommendations. Each step uses study-type-specific prompt templates (x-ray, ultrasound, MRI, CT scan). `stream_report` emits SSE-compatible JSON fragments. |
| `app/utils/tracing.py` | Thin wrapper around Langfuse; all calls are swallowed on error so a tracing outage never affects the API |
| `app/utils/logger.py` | Structured stdout logging using Python's stdlib `logging` |
| `app/models/` | SQLAlchemy ORM models: `User`, `Case`, `AudioFile`, `Transcription`, `Report` |
| `app/schemas/` | Pydantic v2 request/response schemas with strict mode |
| `alembic/` | Database migration scripts managed by Alembic |

### React frontend (`frontend/`)

| File | Responsibility |
|------|----------------|
| `src/App.tsx` | React Router setup: `/`, `/cases/:id`, `/reports` |
| `src/api/client.ts` | Typed API client functions (`casesApi`, `audioApi`, `reportsApi`) |
| `src/pages/CasesPage.tsx` | List all cases; create new case via `CaseForm` |
| `src/pages/CaseDetailPage.tsx` | Upload audio, view transcriptions, generate/stream report |
| `src/pages/ReportsPage.tsx` | All reports overview |
| `src/components/AudioUploader.tsx` | Drag-and-drop file upload **or** live browser microphone recording via `MediaRecorder` API |
| `src/components/ReportEditor.tsx` | Inline-edit clinical sections; Finalize to read-only |
| `src/components/StreamingReportViewer.tsx` | Consumes the SSE stream and renders tokens progressively |
| `src/components/Layout.tsx` | Top navigation shell |
| `src/types/index.ts` | TypeScript types matching the backend Pydantic schemas |

Vite proxies all `/api/*` requests to `http://localhost:8000` in development, so no CORS configuration is needed locally.

### Transcription microservice (`services/transcription/`)

A standalone FastAPI app that exposes `POST /transcribe`. Accepts a multipart audio file, runs Whisper in a thread pool, and returns `{text, confidence, model}`. Traces via Langfuse. Intended for independent horizontal scaling in production.

### LLM microservice (`services/llm/`)

Configuration (`config.py`) and tracing (`tracing.py`) stubs for a future standalone BioGPT service. The main API currently runs BioGPT in-process.

### PostgreSQL

All persistent state is stored in a single PostgreSQL 16 database (`medispeech`). The schema is managed by Alembic; initial migration is in `alembic/versions/001_initial_schema.py`.

### Langfuse

Optional observability dashboard for LLM traces. Every Whisper transcription and every pipeline step emits a Langfuse generation span. The dashboard runs at `http://localhost:3000` in Docker Compose. If Langfuse is unreachable the API continues to function normally.

---

## 3. Data model

```
users
  id           UUID  PK
  email        TEXT  UNIQUE
  name         TEXT
  created_at   TIMESTAMPTZ

cases
  id           UUID  PK
  user_id      UUID  FK → users.id
  pet_species  TEXT
  pet_breed    TEXT
  study_type   TEXT  (x-ray | ultrasound | MRI | CT scan | other)
  created_at   TIMESTAMPTZ
  updated_at   TIMESTAMPTZ

audio_files
  id               UUID  PK
  case_id          UUID  FK → cases.id
  raw_audio_url    TEXT  (relative upload path)
  duration_seconds FLOAT
  created_at       TIMESTAMPTZ

transcriptions
  id             UUID  PK
  audio_file_id  UUID  FK → audio_files.id
  raw_text       TEXT
  confidence     FLOAT  (nullable)
  model_used     TEXT
  created_at     TIMESTAMPTZ

reports
  id                UUID  PK
  case_id           UUID  FK → cases.id
  transcription_id  UUID  FK → transcriptions.id
  clinical_history  TEXT  (nullable)
  findings          TEXT  (nullable)
  impressions       TEXT  (nullable)
  recommendations   TEXT  (nullable)
  status            TEXT  (draft | final)
  created_at        TIMESTAMPTZ
  updated_at        TIMESTAMPTZ
```

**Cascade behaviour:** `Case` deletion cascades through `AudioFile` → `Transcription` → `Report` at the database level.

---

## 4. API reference

All routes are prefixed with `/api`. Detailed interactive docs at `http://localhost:8000/docs`.

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status": "healthy", ...}` |

### Cases (`/api/cases`)

| Method | Path | Body / Params | Response |
|--------|------|---------------|----------|
| POST | `/api/cases` | `{pet_species, pet_breed, study_type}` | `CaseResponse` 201 |
| GET | `/api/cases` | — | `CaseResponse[]` |
| GET | `/api/cases/{case_id}` | — | `CaseResponse` or 404 |
| PATCH | `/api/cases/{case_id}` | any subset of case fields | `CaseResponse` |
| DELETE | `/api/cases/{case_id}` | — | `{"message": "Case deleted"}` |

### Audio & Transcription (`/api/audio`)

| Method | Path | Body / Params | Response |
|--------|------|---------------|----------|
| POST | `/api/audio/{case_id}/upload` | multipart `file` | `{audio_file_id, transcription_id, text, confidence}` |
| GET | `/api/audio/{case_id}/transcriptions` | — | transcription list |
| GET | `/api/audio/{transcription_id}` | — | transcription object or 404 |

### Transcriptions (`/api/transcriptions`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/transcriptions/{audio_file_id}` | — | `TranscriptionResponse` or 404 |
| PATCH | `/api/transcriptions/{transcription_id}` | `{raw_text}` | `TranscriptionResponse` |

### Reports (`/api/reports`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/reports` | `{transcription_id}` | `ReportResponse` 201 (blocking; waits for full LLM generation) |
| POST | `/api/reports/stream/{transcription_id}` | — | SSE stream (see below) |
| POST | `/api/reports/stream/{transcription_id}/save` | `{clinical_history, findings, impressions, recommendations}` | `ReportResponse` 201 |
| GET | `/api/reports/{case_id}` | — | `ReportResponse` or 404 |
| GET | `/api/reports` | — | `ReportResponse[]` |
| PATCH | `/api/reports/{report_id}` | any subset of report fields | `ReportResponse` |
| POST | `/api/reports/{report_id}/finalize` | — | `ReportResponse` with `status: "final"` |

#### SSE streaming format

`POST /api/reports/stream/{transcription_id}` returns `text/event-stream`. Each `data:` line is a JSON object:

```
data: {"section": "clinical_history", "status": "start"}
data: {"section": "clinical_history", "token": "5yo "}
data: {"section": "clinical_history", "token": "Labrador "}
...
data: {"section": "clinical_history", "status": "done", "text": "5yo Labrador. Hip pain x 2 weeks."}
data: {"section": "findings", "status": "start"}
...
data: {"status": "complete", "clinical_history": "...", "findings": "...", "impressions": "...", "recommendations": "..."}
```

After the stream closes, call `POST /api/reports/stream/{transcription_id}/save` with the accumulated section texts to persist the report.

---

## 5. Running locally (development)

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose (for PostgreSQL + Langfuse)
- [`uv`](https://github.com/astral-sh/uv) package manager

### Step 1 — Start infrastructure

```bash
docker compose up -d postgres langfuse-postgres langfuse-server
```

This starts:
- PostgreSQL at `localhost:5432` (`medispeech` database)
- Langfuse at `http://localhost:3000`

### Step 2 — Install backend dependencies

```bash
cd backend
uv sync
```

### Step 3 — Configure environment

```bash
cp .env.example .env   # or create .env manually
```

Minimum `.env` for local development (defaults already work if you use docker-compose):

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/medispeech
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-dev
LANGFUSE_SECRET_KEY=sk-lf-dev
```

### Step 4 — Run database migrations

```bash
cd backend
uv run alembic upgrade head
```

### Step 5 — Start the API

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### Step 6 — Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`. Vite proxies `/api/*` to `http://localhost:8000` automatically.

---

## 6. Running with Docker Compose

This builds the API from the local `backend/Dockerfile` and starts everything together.

```bash
docker compose up --build
```

Services:

| Service | URL | Description |
|---------|-----|-------------|
| API | `http://localhost:8000` | FastAPI + Whisper + BioGPT |
| Langfuse | `http://localhost:3000` | Observability dashboard |
| PostgreSQL | `localhost:5432` | Application database |

The API container volume-mounts `./backend/app` so code changes are picked up immediately (Uvicorn runs with `--reload`).

---

## 7. Running tests

The test suite uses **SQLite in-memory** for the database so no external infrastructure is required.

```bash
cd backend
uv run pytest tests/ -v
```

### Test structure

```
tests/
├── conftest.py                   # in-memory SQLite engine + TestClient fixture
├── test_audio_pipeline.py        # case CRUD + health check
└── test_routes/
│   ├── test_health.py            # health endpoint
│   ├── test_audio.py             # audio upload (Whisper mocked), transcription listing
│   ├── test_transcriptions.py    # transcription read + user-edit
│   └── test_reports.py           # report CRUD, finalize, LLM integration
└── test_services/
    ├── test_audio_service.py     # AudioService unit tests (Whisper mocked)
    └── test_langgraph_service.py # ClinicalWorkflow unit tests (LLM mocked)
```

### What is mocked vs real

| Layer | In tests |
|-------|----------|
| Database | SQLite in-memory (via `aiosqlite`) |
| Whisper (`audio_service.transcribe`) | `unittest.mock.AsyncMock` — no model loaded |
| BioGPT (`llm_service.generate` / `generate_stream`) | `monkeypatch` stub — no model loaded |
| Langfuse | Disabled automatically (connection refused → `LANGFUSE_ENABLED = False`) |

The `test_create_report` test is automatically skipped when the BioGPT model is not present (CI-safe).

### Running specific subsets

```bash
# Route tests only
uv run pytest tests/test_routes/ -v

# Service unit tests only
uv run pytest tests/test_services/ -v

# Single test file
uv run pytest tests/test_routes/test_audio.py -v

# Integration-tagged tests only
uv run pytest -m integration -v
```

---

## 8. Kubernetes deployment

Manifests live in `k8s/`. They target a namespace called `medispeech`.

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/postgres-pvc.yaml
kubectl apply -f k8s/postgres-deployment.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/ingress.yaml
```

The API deployment runs 3 replicas and reads `DATABASE_URL` from a Kubernetes Secret named `database-url`. Create it before applying:

```bash
kubectl create secret generic database-url \
  --from-literal=url="postgresql+asyncpg://user:pass@postgres:5432/medispeech" \
  -n medispeech
```

The Ingress assumes an Nginx Ingress Controller is installed and exposes the API at the configured hostname.

---

## 9. Environment variables

All variables are read by `app/config.py` (pydantic-settings). They can be set in a `.env` file or as real environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/medispeech` | Async PostgreSQL connection string |
| `API_HOST` | `localhost` | Bind address for Uvicorn |
| `API_PORT` | `8000` | Bind port for Uvicorn |
| `API_TITLE` | `MediSpeech API` | OpenAPI title |
| `API_VERSION` | `0.1.0` | API version string |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `WHISPER_MODEL_PATH` | `/models/whisper-base` | Path hint (model name resolved by `whisper.load_model("base")`) |
| `LLM_MODEL_PATH` | `/models/biogpt` | Path hint (HuggingFace resolves `microsoft/BioGPT`) |
| `LANGFUSE_HOST` | `http://localhost:3000` | Langfuse server URL |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-dev` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | `sk-lf-dev` | Langfuse secret key |

---

## 10. Observability (Langfuse)

MediSpeech traces every ML call through Langfuse. Each API request that involves the ML pipeline creates a **trace** with one or more **generation spans**:

| Trace name | Spans | Triggered by |
|------------|-------|--------------|
| `transcription` | `whisper-transcription` | `POST /api/audio/{case_id}/upload` |
| `report-create` | `extract_history`, `generate_findings`, `generate_impressions`, `generate_recommendations` | `POST /api/reports` |
| `report-generation-stream` | same 4 steps | `POST /api/reports/stream/{transcription_id}` |

Langfuse records prompt text, generated output, token counts, and wall-clock latency per step. Access the dashboard at `http://localhost:3000` (Docker Compose) and log in with the credentials you configured in `docker-compose.yml`.

If the Langfuse server is unreachable at startup, tracing is silently disabled (`LANGFUSE_ENABLED = False`) and the API operates normally — tracing is always best-effort.
