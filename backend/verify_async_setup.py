#!/usr/bin/env python
"""Verify async job infrastructure is set up correctly."""
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_dependencies():
    """Verify required packages are importable."""
    logger.info("Checking dependencies...")
    deps = {
        "sqlalchemy": "SQLAlchemy",
        "alembic": "Alembic",
        "celery": "Celery",
        "redis": "Redis client",
        "fitz": "PyMuPDF",
    }
    failed = []
    for module, name in deps.items():
        try:
            __import__(module)
            logger.info(f"  ✓ {name}")
        except ImportError:
            logger.error(f"  ✗ {name} (import {module})")
            failed.append(module)
    return len(failed) == 0


def check_database_config():
    """Verify database configuration."""
    logger.info("Checking database configuration...")
    try:
        from app.config import settings
        from app.database import engine, Base

        db_url = settings.database_url
        logger.info(f"  Database URL: {db_url}")

        # Try to connect
        with engine.connect() as conn:
            logger.info("  ✓ Database connection successful")
            return True
    except Exception as e:
        logger.error(f"  ✗ Database connection failed: {e}")
        return False


def check_celery_config():
    """Verify Celery configuration."""
    logger.info("Checking Celery configuration...")
    try:
        from app.config import settings
        from app.celery_app import celery_app

        logger.info(f"  Broker: {settings.celery_broker_url}")
        logger.info(f"  Backend: {settings.celery_result_backend}")
        logger.info(f"  Tasks: {list(celery_app.tasks.keys())}")

        # Check if task is registered
        if "app.tasks.convert_pdf_to_docx" in celery_app.tasks:
            logger.info("  ✓ convert_pdf_to_docx task registered")
            return True
        else:
            logger.error("  ✗ convert_pdf_to_docx task not found")
            return False
    except Exception as e:
        logger.error(f"  ✗ Celery configuration error: {e}")
        return False


def check_models():
    """Verify ORM models."""
    logger.info("Checking ORM models...")
    try:
        from app.models import ConversionJob, JobStatus
        from app.database import Base

        # Check if model is in metadata
        table_names = [table.name for table in Base.metadata.tables.values()]
        if "conversion_jobs" in table_names:
            logger.info("  ✓ ConversionJob model registered")
            logger.info(f"  Job statuses: {[s.value for s in JobStatus]}")
            return True
        else:
            logger.error("  ✗ conversion_jobs table not in metadata")
            return False
    except Exception as e:
        logger.error(f"  ✗ Model check failed: {e}")
        return False


def check_migration_files():
    """Verify migration files exist."""
    logger.info("Checking migration files...")
    alembic_dir = Path(__file__).parent / "alembic" / "versions"
    if alembic_dir.exists():
        migrations = list(alembic_dir.glob("*.py"))
        logger.info(f"  Found {len(migrations)} migration(s)")
        for mig in sorted(migrations):
            logger.info(f"    - {mig.name}")
        return len(migrations) > 0
    else:
        logger.error(f"  ✗ Migration directory not found: {alembic_dir}")
        return False


def check_libreoffice():
    """Verify LibreOffice is available."""
    logger.info("Checking LibreOffice...")
    try:
        from app.config import SOFFICE_PATH

        if SOFFICE_PATH:
            logger.info(f"  ✓ LibreOffice found: {SOFFICE_PATH}")
            return True
        else:
            logger.warning("  ⚠ LibreOffice not found (will fail at conversion time)")
            return False
    except Exception as e:
        logger.error(f"  ✗ LibreOffice check failed: {e}")
        return False


def main():
    """Run all checks."""
    logger.info("=== Async Job Infrastructure Verification ===\n")

    checks = [
        ("Dependencies", check_dependencies),
        ("Database", check_database_config),
        ("ORM Models", check_models),
        ("Migrations", check_migration_files),
        ("Celery", check_celery_config),
        ("LibreOffice", check_libreoffice),
    ]

    results = []
    for name, check_func in checks:
        logger.info("")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Check failed with exception: {e}")
            results.append((name, False))

    logger.info("\n=== Summary ===")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    logger.info(f"Passed: {passed}/{total}")

    for name, result in results:
        status = "✓" if result else "✗"
        logger.info(f"  {status} {name}")

    if passed == total:
        logger.info("\n✓ All checks passed! Ready for testing.")
        return 0
    else:
        logger.error("\n✗ Some checks failed. See above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
