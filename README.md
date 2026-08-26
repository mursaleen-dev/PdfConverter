# PDF Tools

A dashboard of PDF conversion tools (iLovePDF-style) built with a Next.js frontend and a FastAPI backend.

**Implemented:** JPG/PNG/BMP/WEBP → PDF, DOC/DOCX → PDF, Excel → PDF, PowerPoint → PDF, Text → PDF, HTML → PDF (by URL), PDF → JPG/PNG, PDF → Text, PDF → PDF/A, PDF → Word/Excel/PowerPoint, Merge PDF, and Edit PDF (add text, stamps, and signatures).

## Prerequisites

- Python 3.10+
- Node.js 18+
- [LibreOffice](https://www.libreoffice.org/download/download/) (needed for PDF→Word, Office→PDF, and HTML→PDF conversions)
- Docker & Docker Compose (for local async dev with Redis + Celery worker)

## Setup

### Backend (Local Development)

**Terminal 1: Redis + Celery Worker (via Docker Compose)**
```bash
# Start Redis and Celery worker
docker-compose up
```

**Terminal 2: Database Migrations**
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows; source venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# Create/update database schema
alembic upgrade head
```

**Terminal 3: FastAPI Server**
```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

**Environment variables** (create `backend/.env`):
```ini
# LibreOffice path (auto-detected if on PATH, but can be explicit)
SOFFICE_PATH=/path/to/soffice

# Redis/Celery (defaults work if redis is on localhost:6379)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Database (defaults to SQLite; adjust for production)
DATABASE_URL=sqlite:///./app.db
```

**Database migrations** (after schema changes):
```bash
cd backend
alembic revision --autogenerate -m "Descriptive message"
alembic upgrade head
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The frontend expects the API at `http://localhost:8000` (see `frontend/.env.local`).

## API

### Synchronous Conversions
- `POST /api/convert` — multipart form (`file`, `tool`), where `tool` is one of the ids in `frontend/src/lib/tools.ts` / `backend/app/tools_registry.py` (e.g. `jpg-to-pdf`, `pdf-to-jpg`). Returns the converted file (PDF, image, text, or a zip for multi-page rasterization).
- `POST /api/merge` — multipart form (`files`, 2+ PDFs), returns the merged PDF.
- `POST /api/convert-url` — JSON body `{"url": "..."}`, fetches the page server-side (blocking private/loopback/link-local addresses) and returns it as a PDF.
- `POST /api/edit` — multipart form (`file` PDF + `elements` JSON array). Each element specifies `page` (0-indexed), `type` (`text` or `image`), fractional `x/y/width/height` (0–1 relative to page), and type-specific fields (`text`, `fontSize`, `color`, or `image` base64 data URL). Returns the edited PDF.

### Async Conversions (PDF-to-Word)
- `POST /api/convert` with `tool=pdf-to-word` — Async conversion via LibreOffice. Returns **202 Accepted** with `{job_id, status}` for polling.
- `GET /api/jobs/{job_id}` — Poll job status until completion. Returns `{status, error_code?, result_filename?, processing_seconds?}`.
- `GET /api/jobs/{job_id}/download` — Download the DOCX result once job status is `completed`.

See `backend/ASYNC_SETUP_GUIDE.md` for detailed async testing with curl examples.

### Health & Info
- `GET /api/health` — reports whether LibreOffice was resolved.
