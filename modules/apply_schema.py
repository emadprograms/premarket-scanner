import streamlit as st
import libsql_client
import sys
import os

# Create tables
CREATE_KEYS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS gemini_api_keys (
    key_name TEXT PRIMARY KEY NOT NULL,
    key_value TEXT NOT NULL,
    priority INTEGER DEFAULT 10,
    tier TEXT DEFAULT 'free', 
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_STATUS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS gemini_key_status (
    key_hash TEXT PRIMARY KEY NOT NULL,
    rpm_requests INTEGER NOT NULL DEFAULT 0,
    rpm_window_start REAL NOT NULL DEFAULT 0,
    tpm_tokens INTEGER NOT NULL DEFAULT 0,
    strikes INTEGER NOT NULL DEFAULT 0,
    release_time REAL NOT NULL DEFAULT 0
);
"""

CREATE_MODEL_USAGE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS gemini_model_usage (
    key_hash TEXT NOT NULL,
    model_id TEXT NOT NULL,
    rpm_requests INTEGER NOT NULL DEFAULT 0,
    rpm_window_start REAL NOT NULL DEFAULT 0,
    tpm_tokens INTEGER NOT NULL DEFAULT 0,
    rpd_requests INTEGER NOT NULL DEFAULT 0,
    last_used_day TEXT NOT NULL DEFAULT '',
    strikes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key_hash, model_id)
);
"""

def apply_schema():
    print("🚀 Applying V8 Database Schema...")
    try:
        from modules.utils import get_turso_credentials
        db_url, auth_token = get_turso_credentials()
    except Exception as e:
        print(f"❌ Could not load credentials: {e}")
        # Manual fallback for testing if secrets aren't available to script
        db_url = os.environ.get("TURSO_DB_URL")
        auth_token = os.environ.get("TURSO_AUTH_TOKEN")
        if not db_url:
            print("❌ Environment variables TURSO_DB_URL/TURSO_AUTH_TOKEN missing.")
            return

    url = db_url.replace("libsql://", "https://")
    client = libsql_client.create_client_sync(url=url, auth_token=auth_token)
    
    try:
        print("Creating gemini_api_keys table...")
        client.execute(CREATE_KEYS_TABLE_SQL)
        print("Creating gemini_key_status table...")
        client.execute(CREATE_STATUS_TABLE_SQL)
        print("Creating gemini_model_usage table...")
        client.execute(CREATE_MODEL_USAGE_TABLE_SQL)
        print("✅ Schema applied successfully.")
    except Exception as e:
        print(f"❌ Error applying schema: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    apply_schema()
