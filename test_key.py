import requests
import json

API_KEY = "AIzaSyASCSqkreIXeuIE58JzhSZNVJWVrq0mDBE"
MODELS = ["gemini-1.5-flash", "gemini-3-pro-preview", "gemini-2.0-flash-exp"]

print(f"Testing Key: {API_KEY[:10]}...")

for model in MODELS:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
    }
    print(f"\n--- Testing {model} ---")
    try:
        response = requests.post(url, json=payload)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("SUCCESS")
        else:
            print(f"ERROR: {response.text}")
    except Exception as e:
        print(f"EXCEPTION: {e}")
