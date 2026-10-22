"""
App wiring — Member 5 owns frontend shell + deploy, but backend wiring is
coordinated here. This main.py integrates Member 1 (routes), Member 2 (DB),
and Member 4 (realtime) without touching their owned modules.
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import os

from .database import init_db
from .routes import router
from .realtime import manager

app = FastAPI(title="Real-Time Kanban API", version="0.1.0")

# Allow only explicitly configured frontend origins. Set the deployed Vercel
# origin in FRONTEND_ORIGINS; don't append a wildcard in production.
frontend_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
origins = [origin.strip().rstrip("/") for origin in frontend_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

@app.on_event("startup")
def startup_event():
    init_db()

app.include_router(router)

# Custom validation handler so Member 1's error messages match the guide's
# example shape {"detail":"Card title is required"} instead of array wrapper.
# This keeps FastAPI's normal detail string for known business validations.
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # If any error message matches our domain messages, return it as simple string
    for err in errors:
        msg = err.get("msg", "")
        # Strip Pydantic prefix "Value error, "
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        if msg in ("Card title is required",) or msg.startswith("Invalid column_id"):
            return JSONResponse(status_code=422, content={"detail": msg})
    # Otherwise fall back to default FastAPI validation shape (array) for dev debugging
    return JSONResponse(status_code=422, content={"detail": errors})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # keep connection alive; ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
