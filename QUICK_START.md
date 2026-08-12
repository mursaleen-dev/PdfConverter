# Quick Start: PDF-to-Word Async Conversion

Complete async PDF-to-Word conversion is now ready! Follow these steps to test in the browser.

## What Was Built

✅ **Backend Infrastructure**
- SQLAlchemy ORM + Alembic migrations
- Celery task queue + Redis broker
- LibreOffice subprocess wrapper (600s timeout)
- Job tracking database

✅ **API Endpoints**
- `POST /api/convert` (tool=pdf-to-word) → Returns 202 with job_id
- `GET /api/jobs/{job_id}` → Returns current job status
- `GET /api/jobs/{job_id}/download` → Download DOCX result

✅ **Frontend**
- React component for PDF upload
- Polling UI with progress
- Error handling with specific error codes
- Download button when ready

## Setup (4 Steps)

### Step 1: Install Backend Dependencies

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # macOS/Linux

pip install -r requirements.txt
```

### Step 2: Initialize Database

```bash
# Still in backend/ with venv activated
alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.migration] Running upgrade  -> 001, Create conversion_jobs table
```

### Step 3: Start Services (3 Terminals)

**Terminal 1: Redis + Celery Worker**
```bash
cd "E:\Claude Code\Test App"
docker-compose up
```

Wait for: `redis_1  | Ready to accept connections`

**Terminal 2: FastAPI Backend**
```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

Wait for: `Uvicorn running on http://127.0.0.1:8000`

**Terminal 3: Next.js Frontend**
```bash
cd frontend
npm run dev
```

Wait for: `▲ Next.js ... ready - started server on 0.0.0.0:3000`

### Step 4: Test in Browser

Open http://localhost:3000/pdf-to-word in your browser

## Testing Flow

1. **Click to upload or drag-drop a PDF** (under 20MB, max 500 pages)
   - Status: "Uploading file..."
   
2. **Wait for processing**
   - Status: "Converting to Word..."
   - Elapsed time shows
   
3. **Download when ready**
   - Status shows "Success"
   - "Download" button appears
   - DOCX file downloads

## Error Scenarios

If you see these errors, here's what to do:

| Error | Cause | Fix |
|-------|-------|-----|
| "Cannot connect to API" | Backend not running | Run `uvicorn app.main:app --reload --port 8000` |
| "Scanned PDF" | No text layer | Use OCR tool first, then convert |
| "Password protected" | PDF is encrypted | Remove password, re-upload |
| "Timeout" | Took >10 min | Retry, or split PDF |
| Database error | Migrations not run | Run `alembic upgrade head` |
| Job not found | Celery worker missing | Start Redis + Celery worker |

## Quick Verification

Before testing in browser, verify setup:

```bash
cd backend
python verify_async_setup.py
```

Should show: **✓ All checks passed!**

## What Happens Behind the Scenes

```
Browser Upload (frontend/src/components/PdfToWordFlow.tsx)
  ↓
POST /api/convert 
  (file=file.pdf, tool=pdf-to-word)
  ↓
Backend receives:
  ├─ Validates PDF (size, pages, encryption, scanned detection)
  ├─ Creates ConversionJob record
  ├─ Emits Celery task
  └─ Returns 202 Accepted {job_id}
  ↓
Frontend starts polling GET /api/jobs/{job_id}
  ↓
Celery Worker processes (in parallel):
  ├─ Updates status → processing
  ├─ Runs: soffice --headless --convert-to docx input.pdf
  ├─ Handles errors (timeout, scanned, corrupt, etc.)
  └─ Updates job with result path or error
  ↓
Frontend detects completion:
  ├─ Status changes to "completed"
  ├─ Shows download button
  ├─ GET /api/jobs/{job_id}/download → DOCX file
  └─ Browser downloads file
```

## Files Created/Modified

### Backend
- `app/models.py` — ConversionJob ORM model
- `app/database.py` — SQLAlchemy setup
- `app/celery_app.py` — Celery configuration
- `app/converters/libreoffice.py` — LibreOffice wrapper
- `app/tasks.py` — Celery task
- `app/routers/jobs.py` — Status & download endpoints
- `app/routers/convert.py` — Updated for async pdf-to-word
- `app/main.py` — Registered jobs router
- `alembic/versions/001_*.py` — Database migration
- `docker-compose.yml` — Redis + Celery worker
- `backend/Dockerfile.celery` — Worker image
- `.env.example` — Configuration template

### Frontend
- `src/components/PdfToWordFlow.tsx` — Upload + polling UI
- `src/app/pdf-to-word/page.tsx` — Route page

## Debugging

### Check Backend Status

```bash
# Health check
curl http://localhost:8000/api/health
```

### Check Celery Worker

Look in Terminal 1 (docker-compose):
```
celery_worker_1 | [2026-08-03 14:30:01] Task received
celery_worker_1 | [2026-08-03 14:30:15] Task succeeded
```

### Monitor Database

```bash
# From backend directory
sqlite3 app.db "SELECT id, status, source_filename, created_at FROM conversion_jobs ORDER BY created_at DESC LIMIT 5;"
```

### View Logs

- **Frontend errors**: Browser DevTools (F12)
- **API errors**: Terminal 2 (uvicorn output)
- **Celery logs**: Terminal 1 (docker-compose output)
- **Backend full logs**: `backend/app.log` (if logging to file)

## Configuration

Environment variables (create `backend/.env`):

```ini
# Database
DATABASE_URL=sqlite:///./app.db

# Celery + Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# LibreOffice
SOFFICE_PATH=/usr/bin/soffice  # Auto-detected if on PATH

# API
ALLOWED_ORIGINS=http://localhost:3000
MAX_UPLOAD_MB=20
```

## Common Issues

### "RuntimeError: No module named 'sqlalchemy'"

**Fix**: Ensure venv is activated and requirements.txt is installed
```bash
venv\Scripts\activate
pip install -r requirements.txt
```

### "Connection refused" to Redis

**Fix**: Ensure docker-compose is running
```bash
docker-compose up  # in Terminal 1
```

### "No such file or directory: soffice"

**Fix**: Install LibreOffice or set SOFFICE_PATH in .env

**macOS**: `brew install libreoffice`
**Ubuntu**: `sudo apt-get install libreoffice`
**Windows**: Download from https://www.libreoffice.org/download/

### "Database is locked"

**Fix**: Restart backend (venv re-initialization sometimes helps)
```bash
# Kill Terminal 2, then restart:
uvicorn app.main:app --reload --port 8000
```

## Next Steps

Once working, you can:
- Add frontend job history display
- Implement automatic cleanup (files expire after 7 days)
- Add rate limiting by IP/user
- Migrate to PostgreSQL for production
- Use S3/R2 for file storage

## Support Files

See these for more details:
- `backend/ASYNC_SETUP_GUIDE.md` — Comprehensive guide with curl examples
- `backend/IMPLEMENTATION_SUMMARY.md` — Architecture & design decisions
- `backend/verify_async_setup.py` — Automated verification script
- `backend/test_async_flow.py` — End-to-end test script
