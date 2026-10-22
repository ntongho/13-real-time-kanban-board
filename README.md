# Real-Time Kanban Board

A small collaborative task board for a team. Create tasks, move them between **To Do**, **In Progress**, and **Done**, and see saved changes reflected for other connected browsers. The app includes a simple activity history.

## MVP features

- Three seeded workflow columns.
- Create tasks with a required title and optional description.
- Delete a task after an inline confirmation; deletion is recorded in activity history.
- Drag tasks between columns or use the **Move to** selector.
- Persist board and activity data with SQLAlchemy: SQLite locally, PostgreSQL when `DATABASE_URL` is configured.
- Receive `card.created`, `card.moved`, and `card.deleted` events over WebSockets; the frontend refreshes board/activity data after an event.
- Recent activity feed and clear loading/error states.

Authentication, access control, comments, notifications, and custom columns are not included in this MVP. The demo board is shared and unauthenticated; do not put private information on it.

## Architecture

```text
React + Vite frontend
  ├── HTTP requests ──> FastAPI REST API ──> SQLAlchemy ──> SQLite / PostgreSQL
  └── WebSocket /ws <── FastAPI broadcasts after successful database commits
```

The WebSocket connection manager is in memory, so deploy **one backend instance** for this MVP. It does not coordinate events across multiple backend replicas.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer and npm

## Run locally

Open two terminal windows.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

The API creates `backend/kanban.db` and seeds the default columns on startup. The React app allows local origins `http://localhost:5173` and `http://127.0.0.1:5173` by default.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`). The default API is `http://localhost:8000`. To use a different API URL, set `VITE_API_URL` before building/running, for example:

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

PowerShell:

```powershell
$env:VITE_API_URL="http://localhost:8000"
npm run dev
```

## Tests

Backend tests use a disposable database configured by `backend/tests/conftest.py`; they do not use the demo database.

```bash
cd backend
pytest -q
```

The suite covers API behavior, validation, persistence, database constraints and compatibility migration, card deletion and audit history, WebSocket broadcasts to two clients, disconnect cleanup, and configured CORS behavior.

## API and WebSocket contract

- `GET /health`
- `GET /api/boards/demo`
- `POST /api/boards/demo/cards` with `{ "title": "...", "description": "", "column_id": "todo" }`
- `PATCH /api/cards/{card_id}/move` with `{ "column_id": "doing", "position": 0 }`
- `DELETE /api/cards/{card_id}` -> HTTP 204; records a `deleted` activity row and broadcasts the deleted card snapshot.
- `GET /api/boards/demo/activity`
- WebSocket `/ws`: broadcasts `{ "type": "card.created" | "card.moved" | "card.deleted", "card": { ... } }` after successful persistence.

## Deployment

### Backend on Render

This repository includes `render.yaml` for the FastAPI web service. Create/select the service, then configure these environment variables in its dashboard:

- `DATABASE_URL`: connection URL for a managed PostgreSQL database. The app falls back to SQLite locally when unset; avoid relying on a host's temporary filesystem for production data.
- `FRONTEND_ORIGINS`: exact deployed frontend origin, e.g. `https://your-project.vercel.app` (no trailing slash). Set only trusted origins; the API does not enable wildcard CORS.

The service health check is `/health`. Render must allow WebSocket connections to the `/ws` endpoint. Keep one backend instance because the demo connection manager is process-local.

### Frontend on Vercel

Create a Vercel project with **Root Directory** set to `frontend`, framework Vite, build command `npm run build`, and output directory `dist`. Set this environment variable in Vercel:

- `VITE_API_URL`: public backend base URL, e.g. `https://your-api.onrender.com` (no trailing slash).

After deployment, copy the final Vercel origin into backend `FRONTEND_ORIGINS`, redeploy the backend, then verify the deployed board in two separate browser tabs.

Never commit real credentials or production database URLs. `.env.example` files contain examples only.

## Demo checklist

1. Open the deployed board in two browser tabs.
2. Add a task in one tab; confirm it appears in both.
3. Move it to another column; confirm both tabs update.
4. Confirm the activity feed records the actions.
5. Refresh a tab and verify the task remains.
6. Briefly explain the schema, HTTP API, WebSocket event flow, and one-instance limitation.

## Known limitations

- One shared demo board; no user accounts or authorization.
- One backend instance for real-time broadcasts.
- No offline queue; a disconnected browser reconnects and refetches on the next event but does not buffer local edits.
- Drag-and-drop sends a card to the end of a destination column; precise within-column sorting is not part of the MVP.
- Hosted PostgreSQL and frontend/backend deployment must be configured by the team; do not present local-only behavior as a deployed feature.
