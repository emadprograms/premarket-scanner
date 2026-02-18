import streamlit as st
import requests
import json
import time
from backend.engine.key_manager import KeyManager
from backend.engine.utils import AppLogger

AVAILABLE_MODELS = [
    "gemini-3-flash-free",
    "gemini-2.5-flash-free",
    "gemini-2.5-flash-lite-free",
    "gemini-3-pro-paid",
    "gemini-3-flash-paid",
    "gemma-3-27b",
    "gemma-3-12b"
]
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# USER PROVIDED KEY - DIRECT ACCESS
# USER PROVIDED KEY - DIRECT ACCESS
DIRECT_API_KEY = None # Hardcoded key removed. Use KeyManager.


from typing import Union, Optional

def call_gemini_with_rotation(
    prompt: str,
    system_prompt: str,
    logger: AppLogger,
    config_id: str,
    key_manager: KeyManager,
    max_retries=1
) -> tuple[Optional[str], Optional[str]]:

    # --- Safe Logger Handling ---
    def log(msg):
        if logger:
            try: logger.log(msg)
            except Exception: print(msg)
        else:
            print(msg)

    # 1. Estimate Tokens
    estimated_tokens = key_manager.estimate_tokens(prompt + system_prompt)
    log(f"📊 Estimated Tokens: {estimated_tokens}")

    # 4. Execute Request
    MAX_ATTEMPTS = 3
    attempt_logs = []

    for attempt in range(MAX_ATTEMPTS):
        # Re-fetch or fetch key inside loop to allow failover/rotation
        key_name, key_val, wait_time, model_id = key_manager.get_key(config_id, estimated_tokens)

        if wait_time > 0:
            log(f"⏳ CAPACITY REACHED (Retry): Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            key_name, key_val, wait_time, model_id = key_manager.get_key(config_id, estimated_tokens)

        if not key_val:
            history = "\n".join(attempt_logs)
            return None, f"No API keys available for {config_id} tier.\n\nAttempt History:\n{history}"

        gemini_url = f"{API_BASE_URL}/{model_id}:generateContent?key={key_val}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
        }
        headers = {'Content-Type': 'application/json'}

        try:
            log(f"🚀 Sending Request to {model_id} (Attempt {attempt+1}/{MAX_ATTEMPTS}) using {key_name}...")
            start_ts = time.time()
            response = requests.post(gemini_url, headers=headers, data=json.dumps(payload), timeout=90)
            elapsed = time.time() - start_ts
            
            log(f"📡 Response Code: {response.status_code} (Took {elapsed:.2f}s)")

            if response.status_code == 200:
                try:
                    res_json = response.json()
                    text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    log(f"✅ REQUEST SUCCESS ({key_name})")
                    
                    # REPORT USAGE (V8)
                    total_tokens = res_json.get('usageMetadata', {}).get('totalTokenCount', estimated_tokens)
                    key_manager.report_usage(key_val, total_tokens, model_id)
                    
                    return text, None
                except Exception as e:
                    log(f"⚠️ Parsing Failed. Returning Raw: {str(e)}")
                    return None, response.text 
            
            elif response.status_code == 429:
                err_msg = f"Key '{key_name}': 429 Rate Limit - {response.text}"
                attempt_logs.append(err_msg)
                log(f"⚠️ {err_msg}. Rotating...")
                key_manager.report_failure(key_val)
                time.sleep(2)
                continue

            elif response.status_code in [400, 401, 403, 404]:
                err_data = response.text
                err_msg = f"Key '{key_name}': {response.status_code} - {err_data}"
                attempt_logs.append(err_msg)
                log(f"⛔ Fatal: {err_msg}")
                key_manager.report_fatal_error(key_val)
                # 403/404 might be key specific, so we continue to rotate just in case
                # But usually 400 is bad request. Let's rotate.
                continue

            else:
                err_msg = f"Key '{key_name}': {response.status_code} - {response.text}"
                attempt_logs.append(err_msg)
                log(f"⛔ RAW ERROR: {response.text}")
                continue 

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            err_msg = f"Key '{key_name}': Network Error - {str(e)}"
            attempt_logs.append(err_msg)
            log(f"⚠️ {err_msg}")
            
            if attempt < MAX_ATTEMPTS - 1:
                wait_time = 2 * (attempt + 1)
                log(f"⏳ Retrying in {wait_time}s...")
                time.sleep(wait_time)
            
        except Exception as e:
            err_msg = f"Key '{key_name}': Exception - {str(e)}"
            attempt_logs.append(err_msg)
            log(f"💥 {err_msg}")
            
    final_report = "\n".join(attempt_logs)
    return None, f"Failed after {MAX_ATTEMPTS} attempts.\n\n📋 **Attempt Log:**\n{final_report}"

