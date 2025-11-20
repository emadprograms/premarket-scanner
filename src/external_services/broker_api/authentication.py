# src/external_services/broker_api/authentication.py

import requests
from src.config.credentials import load_capital_config
from src.config.constants import CAPITAL_API_URL_BASE

def create_capital_session(log_func):
    log_func("Attempting to create Capital.com session...")
    api_key, identifier, password = load_capital_config()
    if not all([api_key, identifier, password]):
        log_func("<span style='color:red;'>Error: Capital.com secrets missing.</span>")
        return None, None

    try:
        url = f"{CAPITAL_API_URL_BASE}/session"
        headers = {'X-CAP-API-KEY': api_key}
        payload = {"identifier": identifier, "password": password}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        cst = response.headers.get('CST')
        xst = response.headers.get('X-SECURITY-TOKEN')
        if cst and xst:
            log_func("<span style='color:green;'>Capital.com session created.</span>")
            return cst, xst
        log_func("Session failed: CST or XST token missing in response.")
        return None, None
    except requests.exceptions.RequestException as e:
        log_func(f"<span style='color:red;'>Session failed with network error: {e}</span>")
        return None, None
