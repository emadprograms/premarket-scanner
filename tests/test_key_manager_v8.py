import sys
import os
import json
import time

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from backend.engine.key_manager import KeyManager
from backend.engine.utils import get_turso_credentials

def test_key_manager():
    print("🧪 Testing KeyManager V8...")
    db_url, auth_token = get_turso_credentials()
    if not db_url or not auth_token:
        pytest.skip("Turso credentials not available (CI environment)")
    km = KeyManager(db_url, auth_token)
    
    # 1. Add a test key (using a dummy value if none exist)
    print("Checking for existing keys...")
    keys = km.get_all_managed_keys()
    if not keys:
        print("Adding a test key...")
        km.add_key("test-key", "AIza-test", tier='free')
        keys = km.get_all_managed_keys()
    
    if not keys:
        print("❌ Could not create/find any keys.")
        return

    # 2. Test get_key
    print(f"Testing get_key for 'gemini-3-flash-free'...")
    key_name, key_val, wait, model_id = km.get_key('gemini-3-flash-free', estimated_tokens=100)
    print(f"Result: Name={key_name}, Wait={wait}, Model={model_id}")
    
    if key_val:
        # 3. Test report_usage
        print(f"Testing report_usage for {model_id}...")
        km.report_usage(key_val, tokens=150, model_id=model_id)
        
        # 4. Verify stats
        print("Checking stats...")
        stats = km.get_key_stats(key_val, model_id)
        print(f"Stats: {stats}")
        if stats.get('tpm_tokens') == 150:
            print("✅ Usage reporting verified.")
        else:
            print("⚠️ Usage reporting mismatch or table empty.")
    
    # 5. Test FATAL
    print("Testing FATAL limit...")
    _, _, wait_fatal, _ = km.get_key('gemini-3-flash-free', estimated_tokens=500000)
    if wait_fatal == -1.0:
        print("✅ Fatal limit guard verified.")
    else:
        print(f"❌ Fatal limit guard FAILED (Wait={wait_fatal})")

    # 6. Test PERSISTENCE (Cooldown Restoration)
    print("\n🧪 Testing Key Persistence...")
    if key_val:
        # Force a strike in memory/DB
        km.report_failure(key_val)
        km.db_client.close() # Close first instance
        
        # Init new instance
        km2 = KeyManager(db_url, auth_token)
        if key_val in km2.cooldown_keys:
            print(f"✅ Persistence Verified: {key_name} restored to cooldown.")
        else:
            print(f"❌ Persistence FAILED: {key_name} NOT on cooldown after restart.")
        km2.db_client.close()

if __name__ == "__main__":
    test_key_manager()
