from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from datetime import datetime

app = FastAPI(title="Premarket Scanner API", version="1.0.0")

# CORS Configuration — allow Vercel frontend + local dev + ngrok
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Dynamically add Vercel/ngrok origins from env vars if available
import os as _os
_vercel_url = _os.environ.get("FRONTEND_URL", "")
if _vercel_url:
    ALLOWED_ORIGINS.append(_vercel_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permissive for ngrok/dynamic URLs; tighten with ALLOWED_ORIGINS if needed
    allow_methods=["*"],
    allow_headers=["*", "ngrok-skip-browser-warning"],
    allow_credentials=False,  # Must be False when allow_origins=["*"]
    expose_headers=["*"],
)

import sys
import os

# Add the parent directory to sys.path to allow "backend.x" imports even when running from inside the backend folder
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from backend.services.socket_manager import manager

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/")
def read_root():
    return {"status": "online", "service": "Premarket Scanner API"}

@app.get("/api/debug")
def debug():
    return {"status": "debug", "time": str(datetime.now())}

# Routers
from backend.routers import macro, scanner, ranking, system, archive
app.include_router(macro.router, prefix="/api/macro", tags=["Macro"])
app.include_router(scanner.router, prefix="/api/scanner", tags=["Scanner"])
app.include_router(ranking.router, prefix="/api/ranking", tags=["Ranking"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(archive.router, prefix="/api/archive", tags=["Archive"])

log = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    # Start the Capital.com WebSocket service (non-fatal if auth fails)
    try:
        from backend.services.capital_socket import capital_ws
        await capital_ws.start()
        log.info("✅ Capital.com WebSocket service started.")
    except Exception as e:
        log.error(f"⚠️ Capital.com WebSocket failed to start: {e}. Backend will run without live streaming.")

@app.on_event("shutdown")
async def shutdown_event():
    try:
        from backend.services.capital_socket import capital_ws
        await capital_ws.stop()
    except Exception:
        pass

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
