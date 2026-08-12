#!/usr/bin/env python
"""End-to-end test of async PDF-to-Word conversion flow."""
import sys
import time
import json
import requests
from pathlib import Path
from reportlab.pdfgen import canvas

API_BASE = "http://localhost:8000"
POLL_INTERVAL = 1  # seconds
MAX_WAIT_TIME = 60  # seconds


def create_test_pdf(filename: str = "test_async.pdf") -> Path:
    """Create a simple test PDF with text."""
    c = canvas.Canvas(filename)
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, "Test PDF for Async Conversion")
    c.drawString(50, 720, "This PDF contains extractable text.")
    c.drawString(50, 690, "It should convert successfully to DOCX.")
    c.drawString(50, 650, "")
    c.drawString(50, 620, "Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
    c.drawString(50, 590, "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.")
    c.save()
    return Path(filename)


def upload_pdf(pdf_path: Path) -> str | None:
    """Upload PDF and get job_id."""
    print(f"\n1. Uploading {pdf_path.name}...")
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            data = {"tool": "pdf-to-word"}
            response = requests.post(f"{API_BASE}/api/convert", files=files, data=data)

        if response.status_code == 202:
            result = response.json()
            job_id = result.get("job_id")
            print(f"   ✓ Upload successful")
            print(f"   Job ID: {job_id}")
            print(f"   Status: {result.get('status')}")
            return job_id
        else:
            print(f"   ✗ Upload failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return None


def poll_job_status(job_id: str, max_wait: int = MAX_WAIT_TIME) -> dict | None:
    """Poll job status until completion or timeout."""
    print(f"\n2. Polling job status (max wait: {max_wait}s)...")
    start_time = time.time()
    prev_status = None

    while True:
        elapsed = time.time() - start_time
        if elapsed > max_wait:
            print(f"   ✗ Timeout after {max_wait}s")
            return None

        try:
            response = requests.get(f"{API_BASE}/api/jobs/{job_id}")
            if response.status_code == 200:
                job = response.json()
                status = job.get("status")

                if status != prev_status:
                    print(f"   [{elapsed:.1f}s] Status: {status}")
                    prev_status = status

                if status in ("completed", "failed", "cancelled"):
                    print(f"   ✓ Job finished with status: {status}")
                    if job.get("error_code"):
                        print(f"   Error code: {job.get('error_code')}")
                        print(f"   Error message: {job.get('error_message')}")
                    if job.get("processing_seconds"):
                        print(f"   Processing time: {job.get('processing_seconds')}s")
                    return job
                else:
                    # Still processing, wait and retry
                    time.sleep(POLL_INTERVAL)
            else:
                print(f"   ✗ Status check failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return None


def download_result(job_id: str, output_path: str | None = None) -> bool:
    """Download completed job result."""
    print(f"\n3. Downloading result...")
    try:
        response = requests.get(f"{API_BASE}/api/jobs/{job_id}/download")
        if response.status_code == 200:
            # Use Content-Disposition header or default name
            filename = output_path or "converted_output.docx"
            with open(filename, "wb") as f:
                f.write(response.content)
            file_size = len(response.content)
            print(f"   ✓ Downloaded successfully")
            print(f"   Saved to: {filename}")
            print(f"   File size: {file_size} bytes")
            return True
        else:
            print(f"   ✗ Download failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def test_error_scenarios():
    """Test error handling."""
    print(f"\n4. Testing error scenarios...")

    # Test 1: Invalid tool
    print(f"   Testing invalid tool...")
    try:
        response = requests.post(
            f"{API_BASE}/api/convert",
            files={"file": ("test.pdf", b"%PDF-1.4\n", "application/pdf")},
            data={"tool": "invalid-tool"},
        )
        if response.status_code == 400:
            print(f"   ✓ Invalid tool correctly rejected")
        else:
            print(f"   ✗ Expected 400, got {response.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test 2: Non-existent job
    print(f"   Testing non-existent job...")
    try:
        response = requests.get(f"{API_BASE}/api/jobs/non-existent-job-id")
        if response.status_code == 404:
            print(f"   ✓ Non-existent job correctly returns 404")
        else:
            print(f"   ✗ Expected 404, got {response.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test 3: Download queued job (should fail)
    print(f"   Testing download of queued job...")
    pdf_path = create_test_pdf("test_error.pdf")
    job_id = upload_pdf(pdf_path)
    if job_id:
        try:
            response = requests.get(f"{API_BASE}/api/jobs/{job_id}/download")
            if response.status_code == 400:
                print(f"   ✓ Queued job download correctly rejected")
            else:
                print(f"   ✗ Expected 400, got {response.status_code}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
    pdf_path.unlink(missing_ok=True)


def main():
    """Run full test suite."""
    print("=" * 60)
    print("Async PDF-to-Word Conversion - End-to-End Test")
    print("=" * 60)

    # Check API is running
    print("\nChecking API connection...")
    try:
        response = requests.get(f"{API_BASE}/api/health")
        if response.status_code == 200:
            health = response.json()
            print(f"✓ API is running")
            print(f"  LibreOffice available: {health.get('soffice_available')}")
        else:
            print(f"✗ API returned {response.status_code}")
            print("  Make sure FastAPI server is running on port 8000")
            return 1
    except requests.ConnectionError:
        print(f"✗ Cannot connect to API at {API_BASE}")
        print("  Make sure FastAPI server is running: uvicorn app.main:app --reload --port 8000")
        return 1

    # Main test flow
    pdf_path = create_test_pdf()
    print(f"\nCreated test PDF: {pdf_path.name}")

    # Upload
    job_id = upload_pdf(pdf_path)
    if not job_id:
        return 1

    # Poll
    job = poll_job_status(job_id)
    if not job:
        return 1

    if job.get("status") == "completed":
        # Download
        success = download_result(job_id, "converted.docx")
        if not success:
            return 1
    else:
        print(f"\n✗ Job failed with status: {job.get('status')}")
        print(f"  Error: {job.get('error_message')}")
        return 1

    # Error scenarios
    test_error_scenarios()

    # Cleanup
    pdf_path.unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
