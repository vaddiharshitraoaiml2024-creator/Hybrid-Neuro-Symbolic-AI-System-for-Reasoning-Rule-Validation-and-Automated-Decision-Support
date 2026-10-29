# AI Project Builder
React/Vite frontend + FastAPI backend for AI code generation, file preview, ZIP download, and GitHub publishing.

## Setup
1. Python 3.11+, Node 20+.
2. `cd backend && python -m venv .venv`; activate it; `pip install -r requirements.txt`; copy `.env.example` to `.env`.
3. Set `APP_SECRET`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`. For GitHub publishing configure `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and callback `http://localhost:8000/api/github/callback`.
4. Run backend: `uvicorn app.main:app --reload --port 8000`.
5. In another terminal: `cd frontend && npm install && npm run dev`; open http://localhost:5173.

Create a GitHub OAuth App with the callback above. OAuth requests `repo` and `read:user` scopes; GitHub OAuth Apps cannot scope repo access as narrowly as GitHub Apps. Secrets are server-side only. The local SQLite database stores OAuth tokens; protect the host/database and use HTTPS plus `COOKIE_SECURE=true` in production. Add production-grade CSRF protection, rate limiting, token encryption at rest, and a managed database before public deployment.

Image uploads are recognized but OCR is not configured; the API returns a clear error rather than pretending to extract text. Generated code is never executed. Review before running. See `.env.example` for settings.
