import os
from backend.engine.utils import get_turso_credentials
from backend.engine.database import get_db_connection
from backend.engine.key_manager import KeyManager

class AppContext:
    def __init__(self):
        from backend.engine.infisical_manager import InfisicalManager
        import threading
        
        self.db_url, self.auth_token = get_turso_credentials()
        self.turso = get_db_connection(self.db_url, self.auth_token)
        self.key_manager = KeyManager(self.db_url, self.auth_token)
        
        # Auto-Sync Keys from Infisical on Startup (Background Thread)
        def run_sync():
            try:
                print("🧵 Background: Starting Gemini Key Sync...")
                mgr = InfisicalManager()
                self.key_manager.sync_keys_from_infisical(mgr)
                print("✅ Background: Key Sync Complete.")
            except Exception as e:
                print(f"⚠️ Context: Key Sync Failed: {e}")
        
        threading.Thread(target=run_sync, daemon=True).start()
        
    def get_db(self):
        return self.turso
    
    def get_km(self):
        return self.key_manager

# Singleton instance
context = AppContext()
