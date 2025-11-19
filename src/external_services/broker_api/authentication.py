# src/external_services/broker_api/authentication.py

from src.config.credentials import load_capital_config
from src.config.constants import CAPITAL_API_URL_BASE
import requests

def create_capital_session(logger):
    logger.log("Attempting to create Capital.com session...")
    api_key, identifier, password = load_capital_config()
    if not all([api_key, identifier, password]):
        logger.log("<span style='color:red;'>Error: Capital.com secrets missing.</span>")
        return None, None

    try:
        url = f"{CAPITAL_API_URL_BASE}/session"
        headers = {'X-CAP-API-KEY': api_key, 'Content-Type': 'application/json'}
        payload = {"identifier": identifier, "password": password}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        cst = response.headers.get('CST')
        xst = response.headers.get('X-SECURITY-TOKEN')
        if cst and xst:
            logger.log("<span style='color:green;'>Capital.com session created.</span>")
            return cst, xst
        logger.log("Session failed: Token missing.")
        return None, None
    except Exception as e:
        logger.log(f"Session failed: {e}")
        return None, None
