FROM python:3.11-slim

WORKDIR /app

# System dependencies: LibreOffice (headless conversion engine) + fonts so
# converted documents don't fall back to missing-glyph boxes.
RUN apt-get update && apt-get install -y \
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces (Docker SDK) runs the container as a non-root user and
# expects the app on port 7860. HOME=/tmp gives LibreOffice a writable
# profile directory (it insists on one even for headless conversion), and
# the chmod ensures the non-root runtime user can write scratch/temp files
# regardless of which UID the platform assigns.
ENV HOME=/tmp
ENV PORT=7860
EXPOSE 7860
RUN chmod -R 777 /app /tmp

# Apply database migrations (harmless no-op if already applied — SQLite
# file lives in the container and resets on redeploy anyway) then serve.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}
