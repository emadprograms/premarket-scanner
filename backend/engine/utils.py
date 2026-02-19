import os
import logging
from datetime import datetime, timezone

# Setup standard logging
logging.basicConfig(level=logging.INFO)
logger_stdout = logging.getLogger("backend")

class AppLogger:
    def __init__(self, container=None):
        self.container = container # Keep for compatibility, though not used in FastAPI
        self.log_messages = []

    def _get_ts(self):
        """Standardized timestamp for logs."""
        return datetime.now(timezone.utc).strftime('%H:%M:%S')

    def log(self, message: str, level: str = "INFO"):
        ts = self._get_ts()
        icons = {"INFO": "🔵", "WARNING": "⚠️", "ERROR": "❌", "SUCCESS": "✅"}
        icon = icons.get(level.upper(), "🔵")
        
        new_msg = f"{ts}Z: {icon} {message}"
        self.log_messages.append(new_msg)
        
        # Print to stdout/Render logs
        print(new_msg)

    def info(self, message: str): self.log(message, "INFO")
    def warn(self, message: str): self.log(message, "WARNING")
    def error(self, message: str): self.log(message, "ERROR")
    def success(self, message: str): self.log(message, "SUCCESS")

    def log_code(self, data, language='json', title="Data"):
        ts = self._get_ts()
        print(f"{ts}Z: 📜 {title}")
        print(data)

    def flush(self):
        pass

from backend.engine.infisical_manager import InfisicalManager

def get_turso_credentials():
    """
    Retrieves Turso DB credentials.
    Priority: 1. Infisical Secrets, 2. Environment Variables.
    """
    try:
        # 1. Attempt Infisical Logic
        mgr = InfisicalManager()
        db_url = None
        auth_token = None
        
        if mgr.is_connected:
            # Try long slugs first
            db_url = mgr.get_secret("turso_emadprograms_analystworkbench_DB_URL")
            auth_token = mgr.get_secret("turso_emadprograms_analystworkbench_AUTH_TOKEN")
            
            # Fallback to standard names in Infisical
            if not db_url: db_url = mgr.get_secret("TURSO_DB_URL")
            if not auth_token: auth_token = mgr.get_secret("TURSO_AUTH_TOKEN")
        
        # 2. Fallback to direct Environment Variables
        if not db_url: db_url = os.getenv("TURSO_DB_URL")
        if not auth_token: auth_token = os.getenv("TURSO_AUTH_TOKEN")
            
        if db_url and auth_token:
            # Ensure protocol is handled correctly. Force https:// for cloud compatibility.
            if db_url.startswith("libsql://"):
                db_url = db_url.replace("libsql://", "https://")
            elif not db_url.startswith("https://") and not db_url.startswith("http://"):
                db_url = f"https://{db_url}"
                
            return db_url, auth_token
        else:
            print("[ERROR] Database credentials missing (TURSO_DB_URL/TURSO_AUTH_TOKEN)")
            return None, None
            
    except Exception as e:
        print(f"[ERROR] Critical Initialization Error: {e}")
        return None, None
