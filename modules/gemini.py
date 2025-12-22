import streamlit as st
import requests
import json
import time
from modules.key_manager import KeyManager
from modules.utils import AppLogger

AVAILABLE_MODELS = [
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemma-3-27b-it",
    "gemma-3-12b-it"
]
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

def call_gemini_with_rotation(
    prompt: str,
    system_prompt: str,
    logger: AppLogger,
    model_name: str,
    key_manager: KeyManager,
    max_retries=5
) -> tuple[str | None, str | None]:

    if not key_manager:
        logger.log("❌ ERROR: KeyManager not initialized.")
        return None, "System Configuration Error"

    last_error_msg = "No attempts made"

    logger.log(f"🔎 STARTING REQUEST: {model_name} (Max Retries: {max_retries})")

    for i in range(max_retries):
        current_api_key = None
        key_name = "Unknown"

        try:
            # PASS LOGGER TO GET_KEY FOR STEP-BY-STEP LOGS
            key_name, current_api_key, wait_time = key_manager.get_key(target_model=model_name, logger=logger)

            if not current_api_key:
                logger.log(f"⏳ All keys exhausted for {model_name}. Waiting {wait_time:.0f}s...")
                if wait_time > 0 and i < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    return None, f"Global Rate Limit for {model_name}"

            gemini_url = f"{API_BASE_URL}/{model_name}:generateContent?key={current_api_key}"

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
            }
            headers = {'Content-Type': 'application/json'}

            # TIMEOUT INCREASED TO 90s
            logger.log(f"🚀 Sending Request {i+1} using '{key_name}'... URL: {gemini_url[:60]}...")
            start_ts = time.time()
            response = requests.post(gemini_url, headers=headers, data=json.dumps(payload), timeout=90)
            elapsed = time.time() - start_ts
            
            logger.log(f"📡 Response Code: {response.status_code} (Took {elapsed:.2f}s)")

            if response.status_code == 200:
                key_manager.report_success(current_api_key, model_id=model_name)
                try:
                    text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    logger.log("✅ REQUEST SUCCESS")
                    return text, None
                except (KeyError, IndexError) as e:
                    last_error_msg = f"Invalid JSON: {e}"
                    logger.log(f"⚠️ {last_error_msg}")
                    key_manager.report_failure(current_api_key, is_server_error=True)
                    continue

            elif response.status_code == 429:
                last_error_msg = f"429 Rate Limit"
                # LOG FULL DETAILS FOR USER
                try:
                    err_json = response.json()
                    err_detail = err_json.get('error', {}).get('message', 'No details')
                    logger.log(f"⛔ 429 Details: {err_detail}")
                except:
                    logger.log(f"⛔ 429 Raw: {response.text[:200]}")
                    
                if model_name == 'gemini-2.5-pro':
                    logger.log(f"⛔ 429 received for 2.5 Pro. Bypassing Strike (User Request). Rotating key...")
                    key_manager.report_failure(current_api_key, is_server_error=True) # Soft Retry
                else:
                    logger.log(f"⛔ Adding Strike to '{key_name}'. Headers: {dict(response.headers)}")
                    key_manager.report_failure(current_api_key, is_server_error=False)
            
            elif response.status_code == 404:
                last_error_msg = f"404 Not Found (Invalid Model?)"
                logger.log(f"❓ {last_error_msg}: {model_name}")
                key_manager.report_failure(current_api_key, is_server_error=True) 

            elif response.status_code >= 500:
                last_error_msg = f"Server Error {response.status_code}"
                logger.log(f"☁️ {last_error_msg} on '{key_name}'. Body: {response.text[:200]}")
                key_manager.report_failure(current_api_key, is_server_error=True)

            else:
                last_error_msg = f"API Error {response.status_code}"
                logger.log(f"⚠️ {last_error_msg}: {response.text[:100]}")
                key_manager.report_failure(current_api_key, is_server_error=True)

        except Exception as e:
            last_error_msg = f"Exception: {str(e)}"
            logger.log(f"💥 Exception using '{key_name}': {str(e)}")
            if current_api_key:
                key_manager.report_failure(current_api_key, is_server_error=True)

        if i < max_retries - 1:
            wait = 2 ** i
            logger.log(f"💤 Sleeping {wait}s before retry...")
            time.sleep(wait)

    logger.log("❌ MAX RETRIES EXHAUSTED")
    return None, f"Max Retries Exhausted. Last Error: {last_error_msg}"
