
import streamlit as st
import requests
import json

def check_db_raw():
    try:
        secrets = st.secrets["turso"]
        base_url = secrets["db_url"].replace("libsql://", "https://")
        token = secrets["auth_token"]
        
        # Construct Pipeline URL
        url = f"{base_url}/v2/pipeline"
        print(f"Connecting to: {url}...")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Raw Pipeline Query
        sql = "SELECT key_value FROM gemini_api_keys WHERE key_name = 'arshad.emad@01'"
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql}},
                {"type": "close"}
            ]
        }
        
        resp = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            print("Response JSON:")
            print(json.dumps(resp.json(), indent=2))
        else:
            print(f"Error Response: {resp.text}")
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    check_db_raw()
