# MediSpeech

Medical speech transcription and clinical reporting system for veterinary practices.

## Features

- 🎙️ Audio recording and upload
- 📝 Automatic speech-to-text using Whisper
- 📋 Structured clinical report generation
- 🔒 HIPAA-ready architecture
- ☁️ Kubernetes-ready deployment
- 🚀 Production-grade API

## Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- uv package manager

### Development

```bash
# Clone and setup
cd MediSpeech

# Start local environment
docker-compose up -d

# Install Python dependencies
cd backend
uv sync

# Run API
uv run uvicorn app.main:app --reload

# Health check
curl http://localhost:8000/health
```

## Architecture

### Backend
- **Framework**: FastAPI
- **ORM**: SQLAlchemy (async)
- **Database**: PostgreSQL
- **Migrations**: Alembic
- **Package Manager**: uv

### Frontend
- **Framework**: React 18
- **Language**: TypeScript
- **Build Tool**: Vite
- **Package Manager**: npm

### Infrastructure
- **Containerization**: Docker
- **Orchestration**: Kubernetes
- **Load Balancing**: Nginx Ingress
- **Storage**: Persistent Volumes

## Project Structure

```
MediSpeech/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app factory
│   │   ├── config.py         # Configuration
│   │   ├── db.py             # SQLAlchemy setup
│   │   ├── models/           # ORM models
│   │   ├── routes/           # API endpoints
│   │   ├── schemas/          # Pydantic models
│   │   ├── services/         # Business logic
│   │   └── utils/            # Utilities
│   ├── alembic/              # Database migrations
│   ├── tests/                # Test suite
│   ├── pyproject.toml        # Python dependencies
│   ├── Dockerfile
│   └── docker-compose.yml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
├── k8s/                      # Kubernetes manifests
├── CLAUDE.md                 # Development guide
└── README.md
```

## API Endpoints

### Health
- `GET /health` - Service health check

### Cases
- `GET /cases` - List all cases
- `POST /cases` - Create new case
- `GET /cases/{id}` - Get case details
- `PUT /cases/{id}` - Update case
- `DELETE /cases/{id}` - Delete case

### Audio
- `POST /audio/upload` - Upload audio file

### Transcriptions
- `GET /transcriptions/{audio_file_id}` - Get transcription

### Reports
- `GET /reports/{case_id}` - Get clinical report

## Development

### Run Tests
```bash
cd backend
uv run pytest tests/ -v
```

### Linting & Formatting
```bash
cd backend
uv run black app/ tests/
uv run ruff check app/ tests/ --fix
uv run mypy app/
```

### Database Migrations
```bash
cd backend
# Create migration
uv run alembic revision --autogenerate -m "description"
# Apply migrations
uv run alembic upgrade head
```

## Deployment

### Local Docker
```bash
docker-compose up --build
```

### Kubernetes
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/postgres-pvc.yaml
kubectl apply -f k8s/postgres-deployment.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/ingress.yaml
```

## Documentation

- See [CLAUDE.md](./CLAUDE.md) for detailed development guide
- See [backend/README.md](./backend/README.md) for API documentation
- See [frontend/README.md](./frontend/README.md) for frontend guide

## Configuration

Create `.env` file in `backend/` directory:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/medispeech
API_HOST=localhost
API_PORT=8000
LOG_LEVEL=INFO
WHISPER_MODEL_PATH=/models/whisper-base
LLM_MODEL_PATH=/models/biogpt
```

## License

Proprietary - MediSpeech

## Support

For issues and questions, please refer to the project documentation or contact the development team.
