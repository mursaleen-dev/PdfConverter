"""Celery background tasks for async conversion jobs."""
import logging
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import ConversionJob, JobStatus
from app.converters.libreoffice import convert_pdf_to_docx, get_user_facing_error_message

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.convert_pdf_to_docx")
def task_convert_pdf_to_docx(self, job_id: str) -> dict:
    """
    Async task: convert a PDF to DOCX.

    Celery will retry on Exception (max 2 times, 60s delay) and timeout after 600s.

    Args:
        job_id: UUID of ConversionJob record

    Returns:
        {
            "job_id": str,
            "status": str,  # "completed" or "failed"
            "error_code": str | None,
            "result_filename": str | None,
        }
    """
    db = SessionLocal()
    try:
        # Fetch job record
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in database")
            return {
                "job_id": job_id,
                "status": "failed",
                "error_code": "job_not_found",
            }

        # Update status to processing
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.utcnow()
        db.commit()
        logger.info(f"Job {job_id} started processing")

        # Validate files exist
        source_path = Path(job.source_file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Prepare output path
        result_dir = source_path.parent
        result_filename = job.source_filename.rsplit(".", 1)[0] + ".docx"
        result_path = result_dir / result_filename

        # Run conversion
        success, error_code = convert_pdf_to_docx(source_path, result_path)

        if success:
            # Update job with success
            result_size = result_path.stat().st_size
            job.status = JobStatus.COMPLETED
            job.result_filename = result_filename
            job.result_file_path = str(result_path)
            job.result_file_size_bytes = result_size
            job.completed_at = datetime.utcnow()
            job.error_code = None
            job.error_message = None

            # Calculate processing time
            if job.started_at:
                elapsed = (job.completed_at - job.started_at).total_seconds()
                job.processing_seconds = int(elapsed)

            db.commit()
            logger.info(f"Job {job_id} completed successfully: {result_filename} ({result_size} bytes)")
            return {
                "job_id": job_id,
                "status": "completed",
                "error_code": None,
                "result_filename": result_filename,
            }
        else:
            # Update job with failure
            job.status = JobStatus.FAILED
            job.error_code = error_code
            job.error_message = get_user_facing_error_message(error_code)
            job.completed_at = datetime.utcnow()

            if job.started_at:
                elapsed = (job.completed_at - job.started_at).total_seconds()
                job.processing_seconds = int(elapsed)

            db.commit()
            logger.warning(f"Job {job_id} failed with error code: {error_code}")
            return {
                "job_id": job_id,
                "status": "failed",
                "error_code": error_code,
                "result_filename": None,
            }

    except Exception as e:
        logger.error(f"Task error for job {job_id}: {e}")
        if job:
            job.status = JobStatus.FAILED
            job.error_code = "task_exception"
            job.error_message = f"Internal error: {str(e)}"
            job.completed_at = datetime.utcnow()
            if job.started_at:
                elapsed = (job.completed_at - job.started_at).total_seconds()
                job.processing_seconds = int(elapsed)
            db.commit()

        return {
            "job_id": job_id,
            "status": "failed",
            "error_code": "task_exception",
        }
    finally:
        db.close()
