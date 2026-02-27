import os
import logging
from dotenv import load_dotenv

# CRITICAL: Load .env BEFORE any credential lookups
# This ensures INFISICAL_CLIENT_ID, TURSO_DB_URL, etc. are available
load_dotenv()

from backend.engine.utils import get_turso_credentials
from backend.engine.database import get_db_connection
from backend.engine.key_manager import KeyManager

log = logging.getLogger(__name__)

class AppContext:
    def __init__(self):
        from backend.engine.infisical_manager import InfisicalManager
        import threading
        
        self.db_url, self.auth_token = get_turso_credentials()
        
        if not self.db_url:
            log.error("⚠️ AppContext: Turso credentials missing. Backend will start in degraded mode.")
            self.turso = None
            self.key_manager = None
            return
        
        self.turso = get_db_connection(self.db_url, self.auth_token)
        
        try:
            self.key_manager = KeyManager(self.db_url, self.auth_token)
        except Exception as e:
            log.error(f"⚠️ AppContext: KeyManager init failed: {e}. Running without key management.")
            self.key_manager = None

        # Ensure DB Schema is initialized
        if self.turso:
            try:
                from backend.engine.database import init_db_schema
                from backend.engine.utils import AppLogger
                init_db_schema(self.turso, AppLogger(None))
            except Exception as e:
                log.error(f"⚠️ AppContext: Schema init failed: {e}")
            
            # One-time migration: seed aw_economy_cards from local cache if table is empty
            try:
                from backend.engine.database import upsert_economy_card
                import json
                rs = self.turso.execute("SELECT COUNT(*) FROM aw_economy_cards")
                if rs.rows and rs.rows[0][0] == 0:
                    cache_path = "data/economy_card_cache.json"
                    if os.path.exists(cache_path):
                        with open(cache_path, 'r') as f:
                            cache = json.load(f)
                        date_str = cache['timestamp'].split('T')[0]
                        upsert_economy_card(self.turso, date_str, json.dumps(cache['data']))
                        log.info(f"✅ Migrated cached economy card to DB for {date_str}")
            except Exception as e:
                log.warning(f"⚠️ Economy card migration skipped: {e}")
        
        # Auto-Sync Keys from Infisical on Startup (Background Thread)
        if self.key_manager:
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
        if not self.turso:
            raise RuntimeError("Database not available. Check TURSO_DB_URL / TURSO_AUTH_TOKEN credentials.")
        return self.turso
    
    def get_km(self):
        if not self.key_manager:
            raise RuntimeError("KeyManager not available. Check database credentials.")
        return self.key_manager

# Singleton instance
context = AppContext()
