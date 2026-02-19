from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import List
from datetime import datetime

app = FastAPI(title="Premarket Scanner API", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
from backend.routers import macro, scanner, ranking, system, workbench
app.include_router(macro.router, prefix="/api/macro", tags=["Macro"])
app.include_router(scanner.router, prefix="/api/scanner", tags=["Scanner"])
app.include_router(ranking.router, prefix="/api/ranking", tags=["Ranking"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(workbench.router, prefix="/api/workbench", tags=["Workbench"])

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
