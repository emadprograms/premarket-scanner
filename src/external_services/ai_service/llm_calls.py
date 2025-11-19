# src/external_services/ai_service/llm_calls.py

import requests
import json
import time
from src.config.constants import API_URL

def call_gemini_api(prompt: str, api_key: str, system_prompt: str, retries: int = 3, delay_seconds: int = 5) -> tuple[str | None, list[str]]:
    """
    Calls the Gemini API with retries and returns the response text and a list of internal log messages.
    """
    local_logs = []
    api_url = f"{API_URL}?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
    }

    for attempt in range(retries):
        local_logs.append(f"API Attempt {attempt + 1}/{retries} using key '...{api_key[-4:]}'")
        try:
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=90)
            if response.status_code == 200:
                response_json = response.json()
                try:
                    text = response_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    local_logs.append("API call successful.")
                    return text, local_logs
                except (KeyError, IndexError, TypeError) as e:
                    local_logs.append(f"API Error: Could not parse successful response. Error: {e}")
                    return None, local_logs
            
            local_logs.append(f"API Error: Received status code {response.status_code}. Response: {response.text[:200]}")
            if response.status_code in [429, 500, 503]: # Server-side, worth retrying
                time.sleep(delay_seconds * (2 ** attempt))
            else: # Client-side error (like 400, 401, 403), no point retrying
                local_logs.append("API Error: Client-side error. Aborting retries.")
                return None, local_logs
                
        except requests.exceptions.RequestException as e:
            local_logs.append(f"API Error: Network request failed. Error: {e}")
            time.sleep(delay_seconds * (2 ** attempt))

    local_logs.append(f"API Error: Failed after {retries} attempts.")
    return None, local_logs
