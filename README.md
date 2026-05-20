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
        │  REST + SSE + WebSocket (port 5173 in dev, proxied to 8000)
        ▼
┌─────────────────────────────────────────────┐
│   FastAPI API  (:8000)                      │
│                                             │
│  routes/auth.py           JWT auth (register/login)
│  routes/cases.py          Case CRUD         │
│  routes/audio.py          upload → transcribe → store
│                           WebSocket live recording proxy
│  routes/transcription.py  read/edit text    │
│  routes/reports.py        LLM pipeline + SSE│
│                                             │
│  services/audio_service.py  ──httpx──►  Transcription service (:8001)
│  services/llm_service.py    ──httpx──►  LLM service           (:8002)
│  services/langgraph_service.py  4-step clinical workflow       │
│                                             │
│  utils/tracing.py           Langfuse (best-effort)             │
└──────────┬──────────────────────────────────┘
           │  asyncpg
           ▼
┌──────────────────┐   ┌───────────────────────┐
│  PostgreSQL :5432 │   │  Langfuse v2 :3000    │
│  (medispeech DB) │   │  (trace dashboard)    │
└──────────────────┘   └───────────────────────┘

services/
├── transcription/  Whisper microservice (:8001, internal only) — POST /transcribe, WS /ws/transcribe
└── llm/            BioGPT microservice  (:8002, internal only) — POST /generate
```

**ML inference is fully decoupled from the API.** The FastAPI backend contains no ML dependencies — it delegates all model calls over HTTP to the two microservices. This means:

- The API container is small and fast to build (no torch/transformers).
- Each ML service can be scaled, replaced, or updated independently.
- Tests run in milliseconds because there are no models to load.

---

## 2. Component descriptions

### FastAPI backend (`backend/`)

The primary application. Handles all business logic, database access, and orchestration.

| File | Responsibility |
|------|----------------|
| `app/main.py` | Application factory: creates the FastAPI app, registers CORS, mounts routers, runs `create_all` on startup, flushes Langfuse on shutdown |
| `app/config.py` | Typed settings via `pydantic-settings`; reads from `.env` or environment variables |
| `app/db.py` | Async SQLAlchemy engine + `AsyncSession` factory + `get_db` FastAPI dependency |
| `app/routes/cases.py` | CRUD for `Case` records (POST, GET list, GET one, PATCH, DELETE) |
| `app/routes/audio.py` | Accept audio upload → call transcription service → store result in DB; WebSocket live recording proxy; list/get transcriptions |
| `app/routes/transcription.py` | Read and user-edit transcription text (`GET /api/transcriptions/{audio_file_id}`, `PATCH /api/transcriptions/{id}`) |
| `app/routes/reports.py` | Generate a clinical report (blocking `POST /api/reports` or streaming `POST /api/reports/stream/{transcription_id}`); save, update, finalize |
| `app/services/audio_service.py` | HTTP client for the transcription microservice; sends multipart audio and returns a `TranscriptionResult` |
| `app/services/llm_service.py` | HTTP client for the LLM microservice; `generate()` for blocking calls, `generate_stream()` yields words progressively for SSE |
| `app/services/langgraph_service.py` | Four-step clinical pipeline: extract history → generate findings → generate impressions → generate recommendations. Uses study-type-specific prompt templates (x-ray, ultrasound, MRI, CT scan). `stream_report` emits SSE-compatible JSON fragments. |
| `app/utils/tracing.py` | Thin wrapper around Langfuse; all calls are swallowed on error so a tracing outage never affects the API |
| `app/utils/logger.py` | Structured stdout logging using Python's stdlib `logging` |
| `app/models/` | SQLAlchemy ORM models: `User`, `Case`, `AudioFile`, `Transcription`, `Report` |
| `app/schemas/` | Pydantic v2 request/response schemas with strict mode |
| `app/auth.py` | JWT creation/verification and bcrypt password hashing |

### Transcription microservice (`services/transcription/`)

Standalone FastAPI app that owns the Whisper model. The API backend calls it at `POST /transcribe` (blocking) or proxies binary audio chunks via WebSocket at `WS /ws/transcribe` for live recording sessions. Runs Whisper in a `ThreadPoolExecutor` so the async event loop is never blocked. Warms the model at startup.

> This service is **internal only** — its port is not exposed on the host in Docker Compose.

| File | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI app: `GET /health`, `POST /transcribe`, `WS /ws/transcribe` |
| `app/config.py` | Settings: `host`, `port`, `whisper_model`, Langfuse keys |
| `app/tracing.py` | Langfuse best-effort tracing (same pattern as backend) |
| `Dockerfile` | Slim Python 3.12 image with ffmpeg; installs only Whisper deps |
| `pyproject.toml` | Dependencies: `fastapi`, `uvicorn`, `openai-whisper`, `langfuse` |

### LLM microservice (`services/llm/`)

Standalone FastAPI app that owns the BioGPT model. The API backend calls it at `POST /generate` with a JSON body `{prompt, max_length}` and receives `{text, model}`. Runs generation in a `ThreadPoolExecutor`. Warms the model at startup.

> This service is **internal only** — its port is not exposed on the host in Docker Compose.

| File | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI app: `GET /health`, `POST /generate` |
| `app/config.py` | Settings: `host`, `port`, `biogpt_model`, Langfuse keys |
| `app/tracing.py` | Langfuse best-effort tracing |
| `Dockerfile` | Slim Python 3.12 image; installs only torch/transformers deps |
| `pyproject.toml` | Dependencies: `fastapi`, `uvicorn`, `transformers`, `torch`, `langfuse` |

### React frontend (`frontend/`)

| File | Responsibility |
|------|----------------|
| `src/App.tsx` | React Router setup: `/login`, `/register`, `/`, `/cases/:id`, `/reports` |
| `src/api/client.ts` | Typed API client functions (`casesApi`, `audioApi`, `reportsApi`, `authApi`) with JWT injection |
| `src/context/AuthContext.tsx` | JWT auth state; provides `useAuth()` hook throughout the tree |
| `src/pages/LoginPage.tsx` | Login form |
| `src/pages/RegisterPage.tsx` | Registration form |
| `src/pages/CasesPage.tsx` | List all cases; create new case via `CaseForm` |
| `src/pages/CaseDetailPage.tsx` | Upload audio, view transcriptions, generate/stream report |
| `src/pages/ReportsPage.tsx` | All reports overview |
| `src/components/AudioUploader.tsx` | Drag-and-drop file upload **or** live browser microphone recording via WebSocket streaming |
| `src/components/ReportEditor.tsx` | Inline-edit clinical sections; Finalize to read-only |
| `src/components/StreamingReportViewer.tsx` | Consumes the SSE stream and renders tokens progressively |
| `src/components/Layout.tsx` | Top navigation shell with logout |
| `src/types/index.ts` | TypeScript types matching the backend Pydantic schemas |

Vite proxies all `/api/*` requests to `http://localhost:8000` in development, so no CORS configuration is needed locally.

### PostgreSQL

All persistent state is stored in a single PostgreSQL 16 database (`medispeech`). The schema is created automatically on startup via SQLAlchemy's `create_all` — no manual migration step required for development.

### Langfuse (v2)

Optional observability dashboard for LLM traces. Pinned to `langfuse/langfuse:2` — v2 only requires PostgreSQL. v3 requires ClickHouse + MinIO + Redis and is not used here. The dashboard runs at `http://localhost:3000` in Docker Compose. A separate `langfuse-postgres` container is used so Langfuse data is isolated from application data.

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

All endpoints except `/api/auth/*` require `Authorization: Bearer <token>`.

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status": "healthy", ...}` |

### Auth (`/api/auth`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/auth/register` | `{email, name, password}` | `{access_token, token_type}` 201 |
| POST | `/api/auth/login` | `{email, password}` | `{access_token, token_type}` |

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
| POST | `/api/audio/{case_id}/upload/stream` | multipart `file` | SSE stream of `{type: "segment" \| "done" \| "error"}` |
| WS | `/api/audio/{case_id}/ws` | binary audio chunks + `{"type":"end"}` | real-time partial text + final `{transcription_id, audio_file_id}` |
| POST | `/api/audio/preview` | multipart `file` | `{text}` (no DB write) |
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

### Microservice APIs

These are called internally by the FastAPI backend only. They have no host-facing port in Docker Compose.

**Transcription service** (internal: `http://transcription:8001`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/health` | — | `{"status": "healthy", "service": "transcription"}` |
| POST | `/transcribe` | multipart `file` | `{text, confidence, model}` |
| WS | `/ws/transcribe` | binary audio chunks | partial text events + `{"type":"final", ...}` |

**LLM service** (internal: `http://llm:8002`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/health` | — | `{"status": "healthy", "service": "llm"}` |
| POST | `/generate` | `{prompt, max_length}` | `{text, model}` |

---

## 5. Running locally (development)

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- [`uv`](https://github.com/astral-sh/uv) package manager

### Step 1 — Start infrastructure and ML services

```bash
docker compose up -d postgres langfuse-postgres langfuse-server transcription llm
```

This starts:
- PostgreSQL at `localhost:5432` (`medispeech` database)
- Langfuse at `http://localhost:3000`
- Transcription service (internal, no host port) — downloads Whisper `base` model on first start
- LLM service (internal, no host port) — downloads `microsoft/BioGPT` on first start

> The ML services download models from HuggingFace/OpenAI on first boot. Allow a few minutes. Subsequent starts are instant because Docker volumes cache the model weights.

### Step 2 — Install backend dependencies

```bash
cd backend
uv sync
```

The backend has no ML dependencies — install is fast.

### Step 3 — Configure environment

Copy `.env.example` to `.env` (or create it manually). The defaults work with Docker Compose:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/medispeech
TRANSCRIPTION_SERVICE_URL=http://localhost:8001
LLM_SERVICE_URL=http://localhost:8002
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-dev
LANGFUSE_SECRET_KEY=sk-lf-dev
```

### Step 4 — Start the API

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

The API creates all database tables automatically on first startup — no migration step required.

### Step 5 — Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`. Vite proxies `/api/*` to `http://localhost:8000` automatically.

---

## 6. Running with Docker Compose

Builds all services from source and starts the full stack together.

```bash
docker compose up --build
```

Services started:

| Container | URL | Description |
|-----------|-----|-------------|
| `medispeech-api` | `http://localhost:8000` | FastAPI application |
| `medispeech-transcription` | internal only | Whisper transcription service (no host port) |
| `medispeech-llm` | internal only | BioGPT LLM service (no host port) |
| `medispeech-langfuse` | `http://localhost:3000` | Observability dashboard |
| `medispeech-postgres` | `localhost:5432` | Application database |
| `medispeech-langfuse-postgres` | — | Langfuse-only database (internal) |

The API container volume-mounts `./backend/app` so backend code changes are picked up immediately (Uvicorn runs with `--reload`). ML service code changes require a rebuild (`docker compose up --build transcription` or `llm`).

**Start order:** `postgres` → `langfuse-postgres` + `langfuse-server` → `transcription` + `llm` → `api`

---

## 7. Running tests

The test suite uses **SQLite in-memory** for the database and mocks all HTTP calls to microservices. No external infrastructure is required.

```bash
cd backend
uv run pytest tests/ -v
```

Tests complete in under 2 seconds.

### Test structure

```
tests/
├── conftest.py                   # in-memory SQLite engine + TestClient fixture
├── test_audio_pipeline.py        # case CRUD + health check
├── test_routes/
│   ├── test_health.py            # health endpoint
│   ├── test_audio.py             # audio upload (transcription service mocked), listing
│   ├── test_transcriptions.py    # transcription read + user-edit
│   └── test_reports.py           # report CRUD, finalize, LLM integration
└── test_services/
    ├── test_audio_service.py     # AudioService unit tests (httpx mocked)
    └── test_langgraph_service.py # ClinicalWorkflow unit tests (LLM mocked)
```

### What is mocked vs real

| Layer | In tests |
|-------|----------|
| Database | SQLite in-memory (via `aiosqlite`) |
| Transcription service (`audio_service.transcribe`) | `unittest.mock.AsyncMock` — no HTTP call |
| LLM service (`llm_service.generate` / `generate_stream`) | `monkeypatch` stub — no HTTP call |
| `httpx.AsyncClient` in `AudioService` | Patched with `unittest.mock` — no network |
| Langfuse | Disabled automatically (connection refused → `LANGFUSE_ENABLED = False`) |

The `test_create_report` test is automatically skipped when the LLM service is unreachable (CI-safe).

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

> The transcription and LLM services do not yet have k8s manifests. Add a `Deployment` + `Service` for each, then set `TRANSCRIPTION_SERVICE_URL` and `LLM_SERVICE_URL` in the API `configmap.yaml`.

---

## 9. Environment variables

### Required secrets (must be set before running)

These variables have no safe defaults and must be provided in your `.env` or shell environment:

| Variable | Used by | Description |
|----------|---------|-------------|
| `NEXTAUTH_SECRET` | Langfuse (`docker-compose.yml`) | Random secret for NextAuth session signing |
| `SALT` | Langfuse (`docker-compose.yml`) | Random salt for Langfuse password hashing |
| `JWT_SECRET` | FastAPI backend | HS256 signing secret — minimum 32 chars |
| `HF_TOKEN` | Transcription / LLM services | HuggingFace token — required for gated models, optional for public ones |
| `LANGFUSE_PUBLIC_KEY` | Backend + microservices | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | Backend + microservices | Langfuse project secret key |

---

### API (`backend/app/config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/medispeech` | Async PostgreSQL connection string |
| `API_HOST` | `localhost` | Bind address for Uvicorn |
| `API_PORT` | `8000` | Bind port for Uvicorn |
| `API_TITLE` | `MediSpeech API` | OpenAPI title |
| `API_VERSION` | `0.1.0` | API version string |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `TRANSCRIPTION_SERVICE_URL` | `http://localhost:8001` | Base URL of the transcription microservice |
| `LLM_SERVICE_URL` | `http://localhost:8002` | Base URL of the LLM microservice |
| `LANGFUSE_HOST` | `http://localhost:3000` | Langfuse server URL |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-dev` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | `sk-lf-dev` | Langfuse secret key |
| `JWT_SECRET` | *(required in non-dev)* | HS256 signing secret — minimum 32 chars, must not be the default value outside `ENV=development` |
| `JWT_EXPIRE_MINUTES` | `1440` | Token lifetime (default 24 h) |

### Transcription service (`services/transcription/app/config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8001` | Bind port |
| `WHISPER_MODEL` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `LANGFUSE_HOST` | `http://localhost:3000` | Langfuse server URL |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-dev` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | `sk-lf-dev` | Langfuse secret key |

### LLM service (`services/llm/app/config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8002` | Bind port |
| `BIOGPT_MODEL` | `microsoft/BioGPT` | HuggingFace model ID |
| `LANGFUSE_HOST` | `http://localhost:3000` | Langfuse server URL |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-dev` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | `sk-lf-dev` | Langfuse secret key |

---

## 10. Observability (Langfuse)

MediSpeech traces every ML call through Langfuse v2. Each request that involves the ML pipeline creates a **trace** with one or more **generation spans**:

| Trace name | Spans | Where emitted |
|------------|-------|---------------|
| `transcription` | `whisper` | Transcription service, on `POST /transcribe` |
| `report-create` | `extract_history`, `generate_findings`, `generate_impressions`, `generate_recommendations` | API, on `POST /api/reports` |
| `report-generation-stream` | same 4 steps | API, on `POST /api/reports/stream/{id}` |
| `llm-generate` | `biogpt` | LLM service, on each `POST /generate` call |

Langfuse records prompt text, generated output, token counts, and wall-clock latency per step. Access the dashboard at `http://localhost:3000`.

If the Langfuse server is unreachable at startup, tracing is silently disabled (`LANGFUSE_ENABLED = False`) and the API continues to operate normally — tracing is always best-effort.
