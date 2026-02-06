import streamlit as st
import requests
from modules.capital_api import create_capital_session_v2, CAPITAL_API_URL_BASE

# Mock Streamlit for cache
st.cache_resource = lambda func: func

TICKERS_TO_SEARCH = ["Russell", "RTY", "RUT", "US2000"]

def search_epics():
    print("--- SEARCHING CAPITAL.COM EPICS ---")
    cst, xst = create_capital_session_v2()
    if not cst:
        print("❌ Auth Failed")
        return

    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    
    for ticker in TICKERS_TO_SEARCH:
        print(f"\n🔍 Searching for '{ticker}'...")
        try:
            # Search endpoint
            resp = requests.get(
                f"{CAPITAL_API_URL_BASE}/markets",
                params={"searchTerm": ticker},
                headers=headers
            )
            data = resp.json()
            markets = data.get('markets', [])
            
            if not markets:
                print(f"   ❌ No results for {ticker}")
            else:
                # Print top 3 matches
                for m in markets[:3]:
                    print(f"   ✅ Found: {m['epic']} (Name: {m['instrumentName']}, Type: {m['instrumentType']})")
                    
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    search_epics()
