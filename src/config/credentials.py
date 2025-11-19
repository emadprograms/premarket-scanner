# credentials.py
import streamlit as st

def load_gemini_keys() -> list:
    secrets = st.secrets.get("gemini", {})
    return secrets.get("api_keys", [])

def load_turso_config():
    secrets = st.secrets.get("turso", {})
    url = secrets.get("db_url")
    token = secrets.get("auth_token")
    https_url = url.replace("libsql://", "https://") if url else None
    return https_url, token

def load_capital_config():
    secrets = st.secrets.get("capital_com", {})
    return (
        secrets.get("X_CAP_API_KEY"),
        secrets.get("identifier"),
        secrets.get("password"),
    )
