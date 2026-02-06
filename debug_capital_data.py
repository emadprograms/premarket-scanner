import requests
from modules.capital_api import create_capital_session_v2, CAPITAL_API_URL_BASE
from datetime import datetime, timedelta
import pytz

def debug_fetch():
    print("--- DEBUGGING CAPITAL.COM FETCH ---")
    cst, xst = create_capital_session_v2()
    if not cst:
        print("❌ Auth Failed")
        return

    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    
    # Test problematic tickers + one control
    TICKERS = ["SPY", "UUP", "XLC"]
    
    now_utc = datetime.now(pytz.utc)
    # Use the same logic as capital_api.py (16h limit)
    start_utc = now_utc - timedelta(hours=16) 
    
    params = {
        "resolution": "MINUTE", 
        "max": 10,  # Just need to see if ANY data comes back
        'from': start_utc.strftime('%Y-%m-%dT%H:%M:%S'), 
        'to': now_utc.strftime('%Y-%m-%dT%H:%M:%S')
    }
    
    for epic in TICKERS:
        print(f"\n📉 Fetching {epic}...")
        try:
            url = f"{CAPITAL_API_URL_BASE}/prices/{epic}"
            print(f"   URL: {url}")
            resp = requests.get(url, headers=headers, params=params)
            
            print(f"   Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                prices = data.get('prices', [])
                print(f"   ✅ Data Points: {len(prices)}")
                if prices:
                    print(f"   Latest: {prices[-1]['snapshotTime']} | Bid: {prices[-1]['closePrice']['bid']}")
                else:
                    print("   ⚠️ Empty 'prices' list returned.")
            else:
                print(f"   ❌ Error Body: {resp.text}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")

if __name__ == "__main__":
    debug_fetch()
