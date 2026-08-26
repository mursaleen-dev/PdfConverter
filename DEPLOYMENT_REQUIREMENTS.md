# Deployment Requirements — PDF Tools App

Copy the section below into a prompt to research hosting options.

---

I need to deploy a full-stack web app for a free demo. Here are its requirements:

## Frontend
- Next.js 15 (App Router), Node.js 18+
- Static/SSR hosting, no special runtime needs
- Needs one environment variable pointing at the backend API URL

## Backend
- Python 3.10+, FastAPI, served via Uvicorn
- **Must support a custom Docker image** (not just a generic Python buildpack) —
  the app shells out to a system binary that isn't installable via pip
- **Requires LibreOffice installed in the container** (`apt-get install libreoffice
  libreoffice-writer libreoffice-calc libreoffice-impress fonts-liberation` on
  Debian/Ubuntu-based images) — used for headless document conversion
  (`soffice --headless --convert-to ...`)
- RAM: LibreOffice + a Python web process comfortably needs **at least
  512MB–1GB**; less than that risks out-of-memory failures under load
- No GPU needed
- No persistent/durable storage needed — all file I/O is temporary
  (uploads are processed and discarded); a SQLite file is used but is
  disposable (fine if it resets on redeploy)
- No external database or cache service required (Redis/Postgres not needed)
- Needs to expose one HTTP port for the API
- Needs one environment variable for CORS (`ALLOWED_ORIGINS`) pointing at the
  frontend's URL

## What I'm looking for
- **Genuinely free tier** for both frontend and backend hosting
- **No credit card requirement**, if possible — I've already found that
  Render.com and Hugging Face Spaces both now require adding a card/billing
  info to unlock their free Docker-based hosting, even though the free tier
  itself doesn't charge
- Backend host must support **arbitrary Docker images** (not just Python/Node
  buildpacks) since it needs LibreOffice, a large system dependency not
  installable via pip
- This is for a **demo/portfolio project**, not production traffic — cold
  starts, sleep-on-idle, and low request limits are all acceptable tradeoffs

## Question
Which platforms currently offer genuinely free (no card required) hosting
for a Docker container with these requirements? Please note if any option
you suggest has since started requiring billing info, since this changes
frequently.

---
