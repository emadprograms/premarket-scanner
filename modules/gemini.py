import streamlit as st
import requests
import json
import time
from modules.key_manager import KeyManager
from modules.utils import AppLogger

AVAILABLE_MODELS = [
    "gemini-3-pro-paid",
    "gemini-3-flash-paid",
    "gemini-2.5-pro-paid",
    "gemini-2.5-flash-paid",
    "gemini-2.5-flash-lite-paid",
    "gemini-3-flash-free",
    "gemini-2.5-flash-free",
    "gemini-2.5-flash-lite-free",
    "gemma-3-27b",
    "gemma-3-12b"
]
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# USER PROVIDED KEY - DIRECT ACCESS
DIRECT_API_KEY = "AIzaSyASCSqkreIXeuIE58JzhSZNVJWVrq0mDBE"

def call_gemini_with_rotation(
    prompt: str,
    system_prompt: str,
    logger: AppLogger,
    config_id: str,
    key_manager: KeyManager,
    max_retries=1
) -> tuple[str | None, str | None]:

    # 1. Estimate Tokens
    estimated_tokens = key_manager.estimate_tokens(prompt + system_prompt)
    logger.log(f"📊 Estimated Tokens: {estimated_tokens}")

    # 2. Get Key from Manager
    # Use config_id (e.g. 'gemini-3-flash-free') to get the right tier
    key_name, key_val, wait_time, model_id = key_manager.get_key(config_id, estimated_tokens)

    # 3. Handle Manager Response
    if wait_time == -1.0:
        logger.log(f"❌ FATAL: Request too large for {config_id} ({estimated_tokens} tokens).")
        return None, f"Request exceeds model capacity ({estimated_tokens} tokens)."
    
    if wait_time > 0:
        logger.log(f"⏳ CAPACITY REACHED: Waiting {wait_time:.1f}s for {config_id}...")
        time.sleep(wait_time)
        # Re-fetch after wait
        key_name, key_val, wait_time, model_id = key_manager.get_key(config_id, estimated_tokens)
        if wait_time != 0:
            return None, f"Capacity limit. Wait {wait_time:.1f}s."

    if not key_val:
        logger.log(f"❌ No available keys for {config_id}.")
        return None, f"No API keys available for {config_id} tier."

    # 4. Execute Request
    gemini_url = f"{API_BASE_URL}/{model_id}:generateContent?key={key_val}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
    }
    headers = {'Content-Type': 'application/json'}

    MAX_ATTEMPTS = 3
    for attempt in range(MAX_ATTEMPTS):
        try:
            logger.log(f"🚀 Sending Request to {model_id} (Attempt {attempt+1}/{MAX_ATTEMPTS})...")
            start_ts = time.time()
            response = requests.post(gemini_url, headers=headers, data=json.dumps(payload), timeout=90)
            elapsed = time.time() - start_ts
            
            logger.log(f"📡 Response Code: {response.status_code} (Took {elapsed:.2f}s)")

            if response.status_code == 200:
                try:
                    res_json = response.json()
                    text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    logger.log("✅ REQUEST SUCCESS")
                    
                    # REPORT USAGE (V8)
                    total_tokens = res_json.get('usageMetadata', {}).get('totalTokenCount', estimated_tokens)
                    key_manager.report_usage(key_val, total_tokens, model_id)
                    
                    return text, None
                except Exception as e:
                    logger.log(f"⚠️ Parsing Failed. Returning Raw: {str(e)}")
                    return None, response.text 
            
            elif response.status_code == 429:
                logger.log(f"⚠️ Rate Limited (429). Strikes added.")
                key_manager.report_failure(key_val)
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(5)
                    continue
                return None, "Rate Limit Exceeded (429)"

            elif response.status_code in [400, 401, 403]:
                logger.log(f"⛔ Fatal API Error ({response.status_code}): {response.text}")
                key_manager.report_fatal_error(key_val)
                return None, f"API Fatal Error {response.status_code}"

            else:
                logger.log(f"⛔ RAW ERROR: {response.text}")
                return None, response.text

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            logger.log(f"⚠️ Network/Connection Error: {e}")
            if attempt < MAX_ATTEMPTS - 1:
                wait_time = 2 * (attempt + 1)
                logger.log(f"⏳ Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                 return None, f"Network Error: {str(e)}"
        
        except Exception as e:
            logger.log(f"💥 Exception: {e}")
            return None, str(e)
            
    return None, "Unknown Error"
