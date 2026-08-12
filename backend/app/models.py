"""SQLAlchemy ORM models for job tracking and conversion state."""
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy import Column, String, Integer, Text, DateTime, Enum as SQLEnum, Index
from sqlalchemy.dialects.sqlite import JSON
from app.database import Base


class JobStatus(str, Enum):
    """Status of a conversion job."""
    QUEUED = "queued"  # Waiting in queue
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Failed with error
    CANCELLED = "cancelled"  # User or system cancelled


class ConversionJob(Base):
    """
    Tracks a PDF conversion job (PDF→Word, PDF→Excel, etc.).

    This is a generic job table reusable for all conversion types, with
    job_type distinguishing between different conversions (pdf-to-word, etc.).

    Extensible for future features: notifications, webhooks, bulk conversions.
    """
    __tablename__ = "conversion_jobs"

    # Primary identifiers
    id = Column(String(36), primary_key=True)  # UUID
    job_type = Column(String(50), nullable=False, index=True)  # "pdf-to-word", "pdf-to-excel", etc.

    # Status tracking
    status = Column(SQLEnum(JobStatus), nullable=False, default=JobStatus.QUEUED, index=True)
    error_code = Column(String(50), nullable=True)  # "scanned_pdf", "password_protected", etc.
    error_message = Column(Text, nullable=True)  # Human-readable error description

    # File information
    source_filename = Column(String(255), nullable=False)  # Original PDF name (sanitized)
    source_file_size_bytes = Column(Integer, nullable=False)  # For quota/analytics
    source_page_count = Column(Integer, nullable=True)  # Detected during validation
    result_filename = Column(String(255), nullable=True)  # Output filename (e.g., "file.docx")
    result_file_size_bytes = Column(Integer, nullable=True)  # Only set on success

    # Storage paths (local filesystem; can be migrated to S3/R2 later)
    source_file_path = Column(String(512), nullable=True)  # Temp path on disk
    result_file_path = Column(String(512), nullable=True)  # Temp path on disk (after conversion)

    # Conversion parameters (JSON for flexibility without schema changes)
    options = Column(JSON, nullable=True)  # {"font_preservation": true, ...}

    # User context (optional; for future multi-tenant features)
    user_id = Column(String(36), nullable=True)  # For billing/quota tracking
    client_ip = Column(String(45), nullable=True)  # IPv4/IPv6 for rate limiting

    # Lifecycle
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)  # When processing began
    completed_at = Column(DateTime, nullable=True)  # When processing ended
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # When files and record are deleted

    # Celery integration (for status monitoring)
    celery_task_id = Column(String(36), nullable=True, unique=True)  # ID of async Celery task

    # Performance metrics (for monitoring/SLO tracking)
    processing_seconds = Column(Integer, nullable=True)  # Total time in processing

    __table_args__ = (
        # Composite indices for common queries
        Index("ix_job_status_created", "status", "created_at"),
        Index("ix_job_type_status", "job_type", "status"),
        Index("ix_job_expires_at", "expires_at"),  # For cleanup queries
    )

    def __repr__(self) -> str:
        return f"<ConversionJob {self.id}: {self.job_type} {self.status.value}>"

    @property
    def is_terminal(self) -> bool:
        """True if job is in a terminal state (no further changes expected)."""
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)

    @classmethod
    def calculate_expiry(cls, days: int = 7) -> datetime:
        """Calculate expiry time for automatic cleanup."""
        return datetime.utcnow() + timedelta(days=days)
