import sys
import os
import pandas as pd
from datetime import datetime, timezone

# Add root to path
sys.path.append(os.getcwd())

try:
    from backend.engine.capital_api import create_capital_session_v2, fetch_capital_data_range
    from backend.engine.processing import ticker_to_epic
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

class MockLogger:
    def log(self, msg):
        print(f"[LOG] {msg}")

def test_fetch():
    logger = MockLogger()
    print("1. Connecting to Capital.com...")
    cst, xst = create_capital_session_v2()
    
    if not cst:
        print("❌ Auth Failed")
        return

    tickers_to_test = ["QQQ", "SPY", "IWM"]
    
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - pd.Timedelta(minutes=30)
    print(f"   Window: {start_utc} to {now_utc}")

    for ticker in tickers_to_test:
        epic = ticker_to_epic(ticker)
        if epic == ticker and ticker in ["US100", "US500"]:
             pass # Already correct
        
        print(f"\n--- Testing {ticker} -> {epic} ---")
        df = fetch_capital_data_range(epic, cst, xst, start_utc, now_utc, logger)
        
        if df.empty:
            print(f"❌ No Data Returned for {epic}")
        else:
            last_ts = df.iloc[-1]['dt_utc']
            last_price = df.iloc[-1]['Close']
            diff = now_utc - last_ts
            print(f"✅ Data Returned: {len(df)} rows")
            print(f"   Last Timestamp: {last_ts}")
            print(f"   Last Price: {last_price}")
            print(f"   Lag: {diff}")
            
            if abs(diff.total_seconds()) > 600: # > 10 mins
                print("   ⚠️ STALE DATA (Closed Market?)")
            else:
                print("   ✅ Fresh Data")

if __name__ == "__main__":
    test_fetch()
