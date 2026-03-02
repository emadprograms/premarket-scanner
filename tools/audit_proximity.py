import os
import re
import json
import math
import requests
from dotenv import load_dotenv

import sys
if os.getcwd() not in sys.path:
    sys.path.append(os.getcwd())

from backend.engine.utils import get_turso_credentials
from backend.engine.capital_api import create_capital_session_v2, CAPITAL_API_URL_BASE, get_retry_session
from backend.engine.processing import ticker_to_epic, get_live_bars_from_yahoo, calculate_atr

load_dotenv()

def query_turso(db_url, auth_token, sql):
    """Queries Turso via raw HTTP to bypass libsql-client issues."""
    try:
        import requests
        http_base = db_url.replace("libsql://", "https://")
        if not http_base.startswith("http"):
            http_base = f"https://{http_base}"
        http_base = http_base.rstrip("/")
        
        url = f"{http_base}/v2/pipeline"
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "requests": [{"type": "execute", "stmt": {"sql": sql}}]
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        if not results: return []
            
        exec_res = results[0].get("response", {}).get("result", {})
        rows = exec_res.get("rows", [])
        cols = exec_res.get("cols", [])
        
        parsed_rows = []
        for row in rows:
            parsed_row = {}
            for i, col in enumerate(cols):
                val = row[i].get("value")
                parsed_row[col["name"]] = val
            parsed_rows.append(parsed_row)
        return parsed_rows
    except Exception as e:
        print(f"❌ HTTP Query error: {e}")
        return []

def get_capital_quotes(tickers):
    cst, xst = create_capital_session_v2()
    if not cst or not xst: return {}

    epic_to_ticker = {}
    epics = []
    for t in tickers:
        epic = ticker_to_epic(t) 
        epics.append(epic)
        epic_to_ticker[epic] = t
        
    quotes = {}
    session = get_retry_session()
    chunked = [epics[i:i+40] for i in range(0, len(epics), 40)]
    
    for chunk in chunked:
        params = {"epics": ",".join(chunk)}
        res = session.get(f"{CAPITAL_API_URL_BASE}/markets", headers={'CST': cst, 'X-SECURITY-TOKEN': xst}, params=params)
        if res.status_code == 200:
            for m in res.json().get('marketDetails', []):
                epic = m.get('instrument', {}).get('epic')
                snap = m.get('snapshot', {})
                ticker = epic_to_ticker.get(epic, epic)
                
                bid = snap.get('bid', 0.0)
                offer = snap.get('offer', 0.0)
                quotes[ticker] = {'bid': bid, 'ask': offer, 'mid': (bid + offer) / 2}
    return quotes

def calculate_proximity(current_price, plan_a, plan_b, atr):
    if not current_price or (not plan_a and not plan_b): return 999, float('inf'), float('inf'), float('inf')
    
    dist_a = abs(current_price - plan_a) if plan_a else float('inf')
    dist_b = abs(current_price - plan_b) if plan_b else float('inf')
    nearest_dist = min(dist_a, dist_b)
    
    # EXACT UI Math: if ATR > 0 return nearest_dist / atr, else fallback to percentage
    if atr > 0:
        return nearest_dist / atr, dist_a, dist_b, nearest_dist
    return (nearest_dist / current_price) * 100, dist_a, dist_b, nearest_dist

def print_audit_table():
    db_url, auth_token = get_turso_credentials()
    if not db_url or not auth_token:
        print("❌ Error: Turso credentials missing.")
        return

    print("Fetching cards from Turso...")
    sql = "SELECT ticker, company_card_json FROM aw_company_cards ORDER BY date DESC LIMIT 40"
    items = query_turso(db_url, auth_token, sql)
    
    if not items:
        print("No cards found.")
        return

    seen = {}
    for row in items:
        t = row.get('ticker')
        if t and t not in seen:
            seen[t] = row.get('company_card_json', '{}')
            
    tickers_list = list(seen.keys())
    print(f"Fetching Live Capital.com quotes for {len(tickers_list)} tickers...")
    quotes = get_capital_quotes(tickers_list)

    header = f"{'TICKER':<8} | {'PRICE':<8} | {'ATR':<6} | {'PLAN A':<8} | {'PLAN B':<8} | {'DIST A':<7} | {'DIST B':<7} | {'PROX RATIO':<10}"
    print("\n" + "="*85)
    print(f" PROXIMITY CALCULATION AUDIT (VOLATILITY ADJUSTMENT ENGINE)")
    print("="*85)
    print(header)
    print("-" * 85)

    audited_rows = []

    for ticker, card_json in seen.items():
        try:
            card_data = json.loads(card_json)
        except: continue

        quote = quotes.get(ticker)
        if not quote or quote['mid'] <= 0: continue
            
        live_mid = quote['mid']
        
        # Exact Backend Scanner Logic for ATR
        df = get_live_bars_from_yahoo(ticker, days=3, resolution="MINUTE_5")
        atr = calculate_atr(df) if df is not None else 0.0
        
        # Extract plans like in audit_size
        planA_data = card_data.get('openingTradePlan', {})
        planB_data = card_data.get('alternativePlan', {})
        nameA = planA_data.get('planName', '')
        nameB = planB_data.get('planName', '')

        def extract_pivot(name):
            if not name: return None
            m = re.findall(r"\d+\.?\d*", str(name))
            return float(m[0]) if m else None

        plan_a = extract_pivot(nameA)
        plan_b = extract_pivot(nameB)
        
        res = calculate_proximity(live_mid, plan_a, plan_b, atr)
        prox, dist_a, dist_b, min_dist = res
        
        atr_str = f"{atr:.2f}" if atr else "N/A"
        dist_a_str = f"{dist_a:.2f}" if dist_a != float('inf') else "N/A"
        dist_b_str = f"{dist_b:.2f}" if dist_b != float('inf') else "N/A"
        
        audited_rows.append((ticker, live_mid, atr_str, plan_a, plan_b, dist_a_str, dist_b_str, prox, min_dist))

    # Sort by Proximity Score to match Dashboard Ranking
    audited_rows.sort(key=lambda x: x[7])

    for r in audited_rows:
        ticker, live_mid, atr_str, plan_a, plan_b, dist_a_str, dist_b_str, prox, min_dist = r
        pa_str = f"{plan_a:.2f}" if plan_a else "N/A"
        pb_str = f"{plan_b:.2f}" if plan_b else "N/A"
        
        print(f"{ticker:<8} | {live_mid:<8.2f} | {atr_str:<6} | {pa_str:<8} | {pb_str:<8} | {dist_a_str:<7} | {dist_b_str:<7} | {prox:<8.4f}")

    print("="*85 + "\n")
    print("🧠 HOW TO READ PROXIMITY:\n")
    print("- Proximity is NOT raw dollar distance.")
    print("- The Dashboard normalizes absolute distance using Average True Range (ATR).")
    print("- Formula: Proximity = Minimum Distance to Plan / ATR")
    print("- Example: A $5.00 distance on a stock with a $10.00 ATR = 0.5 proximity (Half a bar away).")
    print("- Example: A $1.00 distance on a stock with a $1.00 ATR = 1.0 proximity (A full bar away).")
    print("- As a result, the $5.00 stock will be ranked HIGHER because it is relatively closer to its plan.\n")

if __name__ == "__main__":
    print_audit_table()
