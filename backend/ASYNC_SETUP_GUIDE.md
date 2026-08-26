# Async PDF-to-Word Conversion Setup Guide

This guide walks through setting up and testing the async PDF-to-Word conversion infrastructure.

## Architecture Overview

The system uses:
- **Database (SQLAlchemy + Alembic)**: Tracks job state and results
- **Task Queue (Celery + Redis)**: Manages async conversion jobs
- **Subprocess (LibreOffice soffice)**: Performs PDF→DOCX conversion with timeout
- **API (FastAPI)**: Exposes upload, status polling, and download endpoints

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (for Redis)
- LibreOffice (for PDF conversion)
- All dependencies installed from `requirements.txt`

## Setup Steps

### 1. Install Dependencies

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # macOS/Linux

pip install -r requirements.txt
```

### 2. Verify Dependencies

Run the verification script to check everything is set up:

```bash
python verify_async_setup.py
```

Expected output:
```
=== Async Job Infrastructure Verification ===

Checking dependencies...
  ✓ SQLAlchemy
  ✓ Alembic
  ✓ Celery
  ✓ Redis client
  ✓ PyMuPDF

Checking database configuration...
  Database URL: sqlite:///./app.db
  ✓ Database connection successful

Checking ORM models...
  ✓ ConversionJob model registered
  Job statuses: ['queued', 'processing', 'completed', 'failed', 'cancelled']

Checking migration files...
  Found 1 migration(s)
    - 001_create_conversion_jobs_table.py

Checking Celery configuration...
  Broker: redis://localhost:6379/0
  Backend: redis://localhost:6379/1
  Tasks: ['app.tasks.convert_pdf_to_docx', ...]
  ✓ convert_pdf_to_docx task registered

Checking LibreOffice...
  ✓ LibreOffice found: /usr/bin/soffice

=== Summary ===
Passed: 6/6
  ✓ Dependencies
  ✓ Database
  ✓ ORM Models
  ✓ Migrations
  ✓ Celery
  ✓ LibreOffice

✓ All checks passed! Ready for testing.
```

### 3. Start Infrastructure (Three Terminals)

**Terminal 1: Redis + Celery Worker**
```bash
docker-compose up
```

Wait for output: `redis_1  | Ready to accept connections`

**Terminal 2: Database Migrations**
```bash
cd backend
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.migration] Running upgrade  -> 001, Create conversion_jobs table for async job tracking
```

**Terminal 3: FastAPI Server**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Wait for: `Uvicorn running on http://127.0.0.1:8000`

## Testing

### 1. Create a Test PDF

```bash
# Windows: Create a simple test PDF
python -c "
from reportlab.pdfgen import canvas
c = canvas.Canvas('test.pdf')
c.drawString(100, 750, 'This is a test PDF with text')
c.drawString(100, 700, 'It should be convertible to Word')
c.save()
"
```

Or use any existing PDF file.

### 2. Upload PDF for Conversion

```bash
curl -X POST http://localhost:8000/api/convert \
  -F file=@test.pdf \
  -F tool=pdf-to-word \
  -v
```

Expected response (202 Accepted):
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "message": "Conversion started. Poll GET /api/jobs/{job_id} for status."
}
```

**Save the `job_id` for next steps.**

### 3. Poll Job Status

```bash
curl http://localhost:8000/api/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**While processing:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "job_type": "pdf-to-word",
  "status": "processing",
  "source_filename": "test.pdf",
  "created_at": "2026-08-03T14:30:00.123456",
  "started_at": "2026-08-03T14:30:01.234567"
}
```

**After completion:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "job_type": "pdf-to-word",
  "status": "completed",
  "source_filename": "test.pdf",
  "result_filename": "test.docx",
  "created_at": "2026-08-03T14:30:00.123456",
  "started_at": "2026-08-03T14:30:01.234567",
  "completed_at": "2026-08-03T14:30:15.567890",
  "processing_seconds": 14
}
```

### 4. Download Result

Once `status` is `"completed"`:

```bash
curl -O http://localhost:8000/api/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/download
```

This will download `document.docx` to your current directory.

## Error Scenarios

### Scanned PDF (No Text Layer)

```json
{
  "status": "failed",
  "error_code": "scanned_pdf",
  "error_message": "PDF appears to be a scanned image with no extractable text. Text extraction failed."
}
```

→ User should run through OCR tool first.

### Password-Protected PDF

```json
{
  "status": "failed",
  "error_code": "password_protected",
  "error_message": "PDF is password-protected. Please remove the password and try again."
}
```

### File Too Large

```
HTTP 413 Payload Too Large
```

→ File exceeds 20MB limit.

### Too Many Pages

```
HTTP 422 Unprocessable Entity
{
  "error_code": "page_limit_exceeded",
  "error_message": "PDF exceeds the 500-page limit."
}
```

### Conversion Timeout

```json
{
  "status": "failed",
  "error_code": "conversion_timeout",
  "error_message": "Conversion took too long. The PDF may be too complex."
}
```

→ Celery will auto-retry (up to 2 times).

## Monitoring

### Check Celery Worker Logs

Terminal 1 (docker-compose) shows:
```
celery_worker_1 | [2026-08-03 14:30:01,234] INFO app.tasks: Task app.tasks.convert_pdf_to_docx[abc123] received
celery_worker_1 | [2026-08-03 14:30:05,567] INFO app.tasks: Job abc123 started processing
celery_worker_1 | [2026-08-03 14:30:15,890] INFO app.tasks: Conversion succeeded: test.pdf → test.docx (45678 bytes)
```

### Check FastAPI Logs

Terminal 3 shows:
```
INFO:app.routers.convert: Created job a1b2c3d4-e5f6-7890-abcd-ef1234567890: test.pdf (1234567 bytes, 3 pages)
INFO:app.routers.convert: Emitted Celery task abc123def456 for job a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### Check Database

```bash
sqlite3 app.db "SELECT id, job_type, status, source_filename, result_filename FROM conversion_jobs ORDER BY created_at DESC LIMIT 5;"
```

Example output:
```
a1b2c3d4-e5f6-7890-abcd-ef1234567890|pdf-to-word|completed|test.pdf|test.docx
```

## Configuration

### Environment Variables

Create `backend/.env`:

```ini
# LibreOffice path (auto-detected if on PATH, but can be explicit)
SOFFICE_PATH=/usr/bin/soffice

# Redis/Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Database
DATABASE_URL=sqlite:///./app.db

# API
ALLOWED_ORIGINS=http://localhost:3000
MAX_UPLOAD_MB=20
```

### Timeouts

- **Subprocess timeout**: 600 seconds (10 minutes)
  - Set in `app/celery_app.py`: `task.time_limit = 600`
  - Set in `app/converters/libreoffice.py`: `CONVERSION_TIMEOUT_SECONDS = 600`
- **Page limit**: 500 pages
  - Set in `app/config.py`: `max_pdf_pages = 500`
- **File retention**: 7 days
  - Set in `app/models.py`: `ConversionJob.calculate_expiry(days=7)`

## Cleanup

Files are temporary and live in `/tmp` (or Windows temp). The system does not currently implement automatic cleanup; the frontend should delete files after download.

In production, implement:
1. Cron job: delete files where `expires_at < now()`
2. S3/R2 cleanup: use bucket lifecycle policies

## Troubleshooting

### Celery Task Not Picked Up

**Symptom**: Job stays in `queued` status forever.

**Check 1: Redis is running**
```bash
redis-cli ping
# Should respond: PONG
```

**Check 2: Celery worker is running**
```bash
# Terminal 1 should show:
# worker ready to accept tasks
```

**Check 3: Database is accessible**
```bash
# Terminal 2 should show successful migration
# Terminal 3 should not log connection errors
```

### LibreOffice Not Found

**Symptom**: Job fails with `error_code: "soffice_not_found"`

**Solution**: Install LibreOffice
```bash
# macOS
brew install libreoffice

# Ubuntu/Debian
sudo apt-get install libreoffice

# Windows
# Download from https://www.libreoffice.org/download/download/
```

Then set `SOFFICE_PATH` in `.env` if auto-detection fails.

### Permission Denied on Temp Files

**Symptom**: Job fails with file access errors.

**Solution**: Ensure temp directory is writable
```bash
# Linux/macOS
chmod 1777 /tmp

# Windows: temp dir defaults to %TEMP% (usually writable)
```

### Database Locked (SQLite)

**Symptom**: `database is locked` errors when running migrations or tests in parallel.

**Note**: SQLite is not suitable for production with concurrent writers. For production:
```bash
# Use PostgreSQL instead
DATABASE_URL=postgresql://user:pass@localhost/pdf_converter
```

Then re-run migrations:
```bash
alembic upgrade head
```

## Next Steps

1. **Frontend Integration**: Build React component to upload PDF and poll for status
2. **Result Download**: Add download link in frontend
3. **Job History**: Display list of recent conversions
4. **Production Database**: Migrate from SQLite to PostgreSQL
5. **S3 Storage**: Move temp files to S3 with signed download URLs
6. **Cleanup Scheduler**: Implement Celery Beat for automatic file cleanup
