import json
from datetime import datetime, timezone
import asyncio

class BackendAppLogger:
    """
    API-aware logger that broadcasts messages to WebSocket clients.
    """
    def __init__(self, manager, task_id: str = "default"):
        self.manager = manager
        self.task_id = task_id
        self.log_messages = []

    def _get_ts(self):
        return datetime.now(timezone.utc).strftime('%H:%M:%S')

    async def log(self, message: str, level: str = "INFO"):
        ts = self._get_ts()
        icons = {"INFO": "🔵", "WARNING": "⚠️", "ERROR": "❌", "SUCCESS": "✅"}
        icon = icons.get(level.upper(), "🔵")
        
        msg_obj = {
            "task_id": self.task_id,
            "timestamp": f"{ts}Z",
            "level": level,
            "icon": icon,
            "message": message
        }
        
        payload = json.dumps(msg_obj)
        self.log_messages.append(payload)
        
        # Non-blocking broadcast
        asyncio.create_task(self.manager.broadcast(payload))

    async def info(self, message: str): await self.log(message, "INFO")
    async def warn(self, message: str): await self.log(message, "WARNING")
    async def error(self, message: str): await self.log(message, "ERROR")
    async def success(self, message: str): await self.log(message, "SUCCESS")
