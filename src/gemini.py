import requests
import json
import time
from key_manager import KeyManager
from .utils import AppLogger

AVAILABLE_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

KEY_MANAGER_INSTANCE = None

def initialize_key_manager(db_url, auth_token):
    global KEY_MANAGER_INSTANCE
    if db_url and auth_token:
        KEY_MANAGER_INSTANCE = KeyManager(
            db_url=db_url,
            auth_token=auth_token
        )
    return KEY_MANAGER_INSTANCE

def call_gemini_with_rotation(
    prompt: str,
    system_prompt: str,
    logger: AppLogger,
    model_name: str,
    max_retries=5
) -> tuple[str | None, str | None]:
    """
    Calls the Gemini API using the KeyManager's Acquire-Use-Report loop.
    Replaces the old 'call_gemini_api' function.
    """
    if not KEY_MANAGER_INSTANCE:
        logger.log("❌ ERROR: KeyManager not initialized. Check database credentials.")
        return None, "System Configuration Error"

    for i in range(max_retries):
        current_api_key = None
        key_name = "Unknown"

        try:
            # 1. ACQUIRE: Get Key from Manager (Checking specific model bucket)
            key_name, current_api_key, wait_time = KEY_MANAGER_INSTANCE.get_key(target_model=model_name)

            # Handle global cooldown (all keys exhausted)
            if not current_api_key:
                logger.log(f"⏳ All keys exhausted for {model_name}. Waiting {wait_time:.0f}s... (Attempt {i+1})")
                if wait_time > 0 and i < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    return None, f"Global Rate Limit for {model_name}"

            # Log the Key Name (Glass Box)
            logger.log(f"🔑 Acquired '{key_name}' | Model: {model_name} (Attempt {i+1})")

            # 2. EXECUTE: Make the Request
            # Construct URL dynamically based on selected model
            gemini_url = f"{API_BASE_URL}/{model_name}:generateContent?key={current_api_key}"

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
            }
            headers = {'Content-Type': 'application/json'}

            response = requests.post(gemini_url, headers=headers, data=json.dumps(payload), timeout=90)

            # 3. REPORT: Feedback Loop
            if response.status_code == 200:
                # Report Success to specific model bucket
                KEY_MANAGER_INSTANCE.report_success(current_api_key, model_id=model_name)

                try:
                    text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    return text, None
                except (KeyError, IndexError):
                    logger.log(f"⚠️ Invalid JSON response from Google.")
                    # Malformed JSON is technically a server/protocol error, don't penalize key heavily
                    KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)
                    continue

            elif response.status_code == 429:
                logger.log(f"⛔ 429 Rate Limit on '{key_name}'. Adding Strike.")
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=False)

            elif response.status_code >= 500:
                logger.log(f"☁️ {response.status_code} Server Error on '{key_name}'. No Penalty.")
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)

            else:
                logger.log(f"⚠️ API Error {response.status_code}: {response.text}")
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)

        except Exception as e:
            logger.log(f"💥 Exception using '{key_name}': {str(e)}")
            if current_api_key:
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)

        if i < max_retries - 1:
            time.sleep(2 ** i)

    return None, "Max Retries Exhausted"
