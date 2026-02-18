import streamlit as st
from datetime import datetime, timezone

class AppLogger:
    def __init__(self, container):
        self.container = container
        self.log_messages = []

    def _get_ts(self):
        """Standardized timestamp for logs."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime('%H:%M:%S')

    def log(self, message: str, level: str = "INFO"):
        ts = self._get_ts()
        icons = {"INFO": "🔵", "WARNING": "⚠️", "ERROR": "❌", "SUCCESS": "✅"}
        icon = icons.get(level.upper(), "🔵")
        
        new_msg = f"**{ts}Z:** {icon} {message}"
        self.log_messages.append(new_msg)
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)

    def info(self, message: str): self.log(message, "INFO")
    def warn(self, message: str): self.log(message, "WARNING")
    def error(self, message: str): self.log(message, "ERROR")
    def success(self, message: str): self.log(message, "SUCCESS")

    def log_code(self, data, language='json', title="Data"):
        ts = self._get_ts()
        new_msg = f"**{ts}Z:** 📜 {title} (See code block below)"
        self.log_messages.append(new_msg)
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)
            if language == 'json' and isinstance(data, dict):
                self.container.json(data)
            else:
                self.container.code(str(data), language=language)

    def flush(self):
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)

from backend.engine.infisical_manager import InfisicalManager

def get_turso_credentials():
    try:
        # 1. Attempt Infisical Logic
        mgr = InfisicalManager()
        if mgr.is_connected:
            # SWITCHED TO ANALYST WORKBENCH (Has Keys & Context)
            db_url = mgr.get_secret("turso_emadprograms_analystworkbench_DB_URL")
            auth_token = mgr.get_secret("turso_emadprograms_analystworkbench_AUTH_TOKEN")
            
            if db_url and auth_token:
                # Ensure HTTPS
                return db_url.replace("libsql://", "https://"), auth_token
            else:
                if not db_url: st.error("Infisical: DB_URL secret missing.")
                if not auth_token: st.error("Infisical: AUTH_TOKEN secret missing.")
                return None, None
        else:
            # Note: InfisicalManager now shows its own st.error
            return None, None
        
        # Fallback removed - we strictly want Infisical to work.
    except Exception as e:
        st.error(f"[ERROR] Critical Initialization Error: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None, None
