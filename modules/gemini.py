import streamlit as st
import requests
import json
import time
from modules.key_manager import KeyManager
from modules.utils import AppLogger

AVAILABLE_MODELS = [
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemma-3-27b-it",
    "gemma-3-12b-it"
]
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# USER PROVIDED KEY - DIRECT ACCESS
DIRECT_API_KEY = "AIzaSyASCSqkreIXeuIE58JzhSZNVJWVrq0mDBE"

def call_gemini_with_rotation(
    prompt: str,
    system_prompt: str,
    logger: AppLogger,
    model_name: str,
    key_manager: KeyManager, # Kept for signature compatibility, ignored
    max_retries=1
) -> tuple[str | None, str | None]:

    logger.log(f"🔎 DIRECT REQUEST: {model_name} (Database/KeyManager Bypassed)")
    
    # Check for Manual Override from UI
    current_key = DIRECT_API_KEY
    if 'manual_api_key' in st.session_state and st.session_state.manual_api_key:
         current_key = st.session_state.manual_api_key
         logger.log("🔑 Using MANUAL API Key override.")

    gemini_url = f"{API_BASE_URL}/{model_name}:generateContent?key={current_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
    }
    headers = {'Content-Type': 'application/json'}

    MAX_ATTEMPTS = 3
    for attempt in range(MAX_ATTEMPTS):
        try:
            logger.log(f"🚀 Sending Request to Google (Attempt {attempt+1}/{MAX_ATTEMPTS})...")
            start_ts = time.time()
            response = requests.post(gemini_url, headers=headers, data=json.dumps(payload), timeout=90)
            elapsed = time.time() - start_ts
            
            logger.log(f"📡 Response Code: {response.status_code} (Took {elapsed:.2f}s)")

            if response.status_code == 200:
                try:
                    # Direct Extraction
                    text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    logger.log("✅ REQUEST SUCCESS")
                    return text, None
                except Exception as e:
                    # USER REQUEST: RAW RESPONSE ON ERROR
                    logger.log(f"⚠️ Parsing Failed. Returning Raw: {str(e)}")
                    return None, response.text 
            else:
                # RAW ERROR RETURN
                logger.log(f"⛔ LOGGING RAW ERROR: {response.text}")
                return None, response.text

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            # SPECIFIC HANDLING FOR "Error 443" / NETWORK ISSUES
            logger.log(f"⚠️ Network/Connection Error (Port 443): {e}")
            if attempt < MAX_ATTEMPTS - 1:
                wait_time = 2 * (attempt + 1)
                logger.log(f"⏳ Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                 logger.log(f"💥 Failed after {MAX_ATTEMPTS} attempts.")
                 return None, f"Network Error (Max Retries): {str(e)}"
        
        except Exception as e:
            logger.log(f"💥 Exception: {e}")
            return None, str(e)
            
    return None, "Unknown Error"
