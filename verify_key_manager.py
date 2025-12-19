import os
import logging
from modules.key_manager import KeyManager

# Basic logging setup
logging.basicConfig(level=logging.INFO)

def get_env_var(name):
    try:
        with open('.env') as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.strip().split('=', 1)[1]
    except: return None
    return os.environ.get(name)

url = get_env_var("TURSO_DB_URL")
token = get_env_var("TURSO_AUTH_TOKEN")

try:
    print("Initializing KeyManager...")
    km = KeyManager(db_url=url, auth_token=token)
    print("KeyManager initialized successfully.")
    
    print("Keys found:", km.name_to_key.keys())
    print("Testing get_key for gemini-2.5-flash-lite...")
    key = km.get_key('gemini-2.5-flash-lite')
    print("Got key:", key)
    
except Exception as e:
    print(f"FAILED: {e}")
    exit(1)
