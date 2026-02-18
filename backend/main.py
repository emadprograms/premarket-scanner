from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import List

app = FastAPI(title="Premarket Scanner API", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Routers
from backend.routers import macro, scanner, ranking, system
app.include_router(macro.router, prefix="/api/macro", tags=["Macro"])
app.include_router(scanner.router, prefix="/api/scanner", tags=["Scanner"])
app.include_router(ranking.router, prefix="/api/ranking", tags=["Ranking"])
app.include_router(system.router, prefix="/api/system", tags=["System"])

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
