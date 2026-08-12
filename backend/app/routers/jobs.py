"""Job status and result endpoints for async conversions."""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConversionJob, JobStatus

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str, db: Session = Depends(get_db)) -> dict:
    """
    Get the status of a conversion job.

    Returns:
        {
            "id": "uuid",
            "job_type": "pdf-to-word",
            "status": "queued|processing|completed|failed|cancelled",
            "error_code": "...",  # only if status=failed
            "error_message": "...",  # only if status=failed
            "source_filename": "...",
            "result_filename": "...",  # only if status=completed
            "created_at": "2026-08-03T...",
            "started_at": "...",  # only if status=processing/completed/failed
            "completed_at": "...",  # only if status=completed/failed
            "processing_seconds": 42,  # only if completed/failed
        }
    """
    job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status.value,
        "source_filename": job.source_filename,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }

    # Include optional fields based on status
    if job.started_at:
        response["started_at"] = job.started_at.isoformat()

    if job.completed_at:
        response["completed_at"] = job.completed_at.isoformat()

    if job.processing_seconds is not None:
        response["processing_seconds"] = job.processing_seconds

    if job.result_filename:
        response["result_filename"] = job.result_filename

    if job.error_code:
        response["error_code"] = job.error_code

    if job.error_message:
        response["error_message"] = job.error_message

    return response


@router.get("/api/jobs/{job_id}/download")
async def download_job_result(job_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """
    Download the result file of a completed job.

    Returns the converted file if job is completed, 404 if not found,
    and 400 if job is still processing or failed.
    """
    job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is {job.status.value} (not completed). Cannot download."
        )

    result_path = Path(job.result_file_path)
    if not result_path.exists():
        logger.error(f"Result file missing for completed job {job_id}: {result_path}")
        raise HTTPException(status_code=500, detail="Result file not found on disk")

    return FileResponse(
        result_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=job.result_filename or "document.docx",
    )
