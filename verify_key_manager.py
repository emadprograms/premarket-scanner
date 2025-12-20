import os
import logging
import requests
from modules.key_manager import KeyManager

# Basic logging setup
logging.basicConfig(level=logging.INFO)

def get_env_var(name):
    # Try .env first
    try:
        with open('.streamlit/secrets.toml') as f:
            for line in f:
                if "TURSO_DB_URL" in line:
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
                if "TURSO_AUTH_TOKEN" in line:
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except: pass
    
    return os.environ.get(name)

# Hardcoded fallback for testing if env fails
url = "libsql://premarket-scanner-emadprograms.turso.io"
token = "ey..." # Value hidden, will load from secrets in prod context usually

# Try to find secrets from file manually if needed
try:
    with open('.streamlit/secrets.toml', 'r') as f:
        content = f.read()
        import re
        url_match = re.search(r'TURSO_DB_URL\s*=\s*"(.*?)"', content)
        token_match = re.search(r'TURSO_AUTH_TOKEN\s*=\s*"(.*?)"', content)
        if url_match: url = url_match.group(1)
        if token_match: token = token_match.group(1)
except: pass

# FORCE HTTPS
if "libsql://" in url:
    url = url.replace("libsql://", "https://")

print(f"URL: {url}")

try:
    print(f"Testing connectivity to {url}...")
    resp = requests.get(url, timeout=5)
    print(f"HTTP Status: {resp.status_code}")
    print(f"HTTP Text: {resp.text[:100]}")
except Exception as e:
    print(f"HTTP Request Failed: {e}")

class ConsoleLogger:
    def log(self, message):
        print(f"[LOG] {message}")

try:
    print("Initializing KeyManager...")
    km = KeyManager(db_url=url, auth_token=token)
    print("KeyManager initialized successfully.")
    
    print("--- KEY METADATA ---")
    for k, v in km.name_to_key.items():
        meta = km.key_metadata.get(v, {})
        print(f"Key: {k} | Tier: {meta.get('tier', 'N/A')}")

    print("\n--- TESTING GEMINI 2.5 PRO ---")
    logger = ConsoleLogger()
    key_name, key_val, wait = km.get_key('gemini-2.5-pro', logger=logger)
    print(f"RESULT: Name={key_name}, Wait={wait}")
    
except Exception as e:
    print(f"FAILED: {e}")
