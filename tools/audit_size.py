import json
import os
import math
import re
import logging
import requests
from dotenv import load_dotenv

# CRITICAL: Load .env BEFORE any lookups
load_dotenv()

# Add the parent directory to sys.path to allow "backend.x" imports
import sys
if os.getcwd() not in sys.path:
    sys.path.append(os.getcwd())

from backend.engine.utils import get_turso_credentials
from backend.engine.capital_api import create_capital_session_v2, CAPITAL_API_URL_BASE, get_retry_session
from backend.engine.processing import ticker_to_epic

logging.basicConfig(level=logging.ERROR)
log = logging.getLogger("audit_size")

def query_turso(db_url, auth_token, sql):
    """Queries Turso via raw HTTP to bypass libsql-client issues."""
    try:
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
    """Fetches Live Bid/Ask from Capital.com for the given tickers."""
    cst, xst = create_capital_session_v2()
    if not cst or not xst:
        print("❌ Could not establish Capital.com session.")
        return {}

    epic_to_ticker = {}
    epics = []
    
    for t in tickers:
        epic = ticker_to_epic(t) 
        epics.append(epic)
        epic_to_ticker[epic] = t
        
    session = get_retry_session()
    chunked = [epics[i:i+40] for i in range(0, len(epics), 40)]
    
    quotes = {}
    for chunk in chunked:
        params = {"epics": ",".join(chunk)}
        res = session.get(f"{CAPITAL_API_URL_BASE}/markets", headers={'CST': cst, 'X-SECURITY-TOKEN': xst}, params=params)
        if res.status_code == 200:
            details = res.json().get('marketDetails', [])
            for m in details:
                epic = m.get('instrument', {}).get('epic')
                snap = m.get('snapshot', {})
                ticker = epic_to_ticker.get(epic, epic)
                quotes[ticker] = {
                    'bid': snap.get('bid', 0.0),
                    'ask': snap.get('offer', 0.0),
                }
    return quotes

def extract_best_invalidation(invalidation_text, entry_price):
    if not invalidation_text or entry_price is None or entry_price <= 0: return None
    matches = re.findall(r"\d+\.?\d*", str(invalidation_text))
    if not matches: return None
    
    # Exact frontend logic: Find number nearest to entry_price
    best_price = float(matches[0])
    best_diff = abs(entry_price - best_price)
    
    for m in matches[1:]:
        p = float(m)
        d = abs(entry_price - p)
        if d < best_diff:
            best_diff = d
            best_price = p
            
    return best_price

def get_plan_target_level(plan_name):
    """Extracts the target pivot from the plan name."""
    matches = re.findall(r"\d+\.?\d*", str(plan_name))
    if not matches: return None
    return float(matches[0])

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

    # Settings
    account_amount = 10000
    risk_percentage = 1.0
    risk_dollars = (account_amount * risk_percentage) / 100

    header = f"{'TICKER':<8} | {'BID':<8} | {'ASK':<8} | {'NATURE':<10} | {'ENTRY':<8} | {'INVALID':<8} | {'DIST':<6} | {'RISK$':<5} | {'SHARES':<6} | {'PLAN'}"
    print("\n" + "="*115)
    print(f" POSITION SIZE CALCULATION AUDIT (CAPITAL.COM BID/ASK + EXACT UI LOGIC)")
    print("="*115)
    print(header)
    print("-" * 115)

    for ticker, card_json in seen.items():
        try:
            card_data = json.loads(card_json)
        except: continue
        
        quote = quotes.get(ticker)
        if not quote: 
            continue
            
        live_bid = quote['bid']
        live_ask = quote['ask']
        if not live_bid or not live_ask: continue
        
        live_mid = (live_bid + live_ask) / 2
        if live_mid <= 0: continue

        planA = card_data.get('openingTradePlan', {})
        planB = card_data.get('alternativePlan', {})
        
        nameA = planA.get('planName', '')
        nameB = planB.get('planName', '')
        
        pivotA = get_plan_target_level(nameA)
        pivotB = get_plan_target_level(nameB)
        
        active_plan = None
        active_name = ""
        nearest_level = live_mid
        
        if pivotA is not None and pivotB is not None:
            distA = abs(live_mid - pivotA)
            distB = abs(live_mid - pivotB)
            if distA <= distB:
                active_plan = planA
                active_name = nameA
                nearest_level = pivotA
            else:
                active_plan = planB
                active_name = nameB
                nearest_level = pivotB
        elif pivotA is not None:
            active_plan = planA
            active_name = nameA
            nearest_level = pivotA
        else:
            active_plan = planA
            active_name = nameA
            
        nature_str = "RESISTANCE"
        if "support" in active_name.lower() or "long" in active_name.lower() or "bull" in active_name.lower():
            nature_str = "SUPPORT"
        elif "resistance" in active_name.lower() or "short" in active_name.lower() or "bear" in active_name.lower():
            nature_str = "RESISTANCE"
        else: 
            if nearest_level < live_mid:
                nature_str = "SUPPORT"
            else:
                nature_str = "RESISTANCE"
                
        is_support = (nature_str == "SUPPORT")
        
        # EXACT UI SPREAD LOGIC
        entry_price = live_ask if is_support else live_bid
        
        inv_text = active_plan.get('invalidation', "")
        best_inv_price = extract_best_invalidation(inv_text, entry_price)
        
        if best_inv_price and entry_price > 0:
            if is_support:
                actual_distance = entry_price - best_inv_price
            else:
                actual_distance = best_inv_price - entry_price
                
            if actual_distance <= 0:
                print(f"{ticker:<8} | {live_bid:<8.2f} | {live_ask:<8.2f} | {nature_str:<10} | {entry_price:<8.2f} | {best_inv_price:<8.2f} | {'N/A':<6} | {risk_dollars:<5.0f} | {'N/A':<6} | {str(inv_text)[:30]}...")
            else:
                spread = abs(live_ask - live_bid)
                distance = max(actual_distance, spread)
                shares = math.floor(risk_dollars / distance) if distance > 0 else 0
                print(f"{ticker:<8} | {live_bid:<8.2f} | {live_ask:<8.2f} | {nature_str:<10} | {entry_price:<8.2f} | {best_inv_price:<8.2f} | {distance:<6.2f} | {risk_dollars:<5.0f} | {shares:<6} | {str(inv_text)[:30]}...")
        else:
            print(f"{ticker:<8} | {live_bid:<8.2f} | {live_ask:<8.2f} | {nature_str:<10} | {entry_price:<8.2f} | {'N/A':<8} | {'N/A':<6} | {risk_dollars:<5.0f} | {'N/A':<6} | {str(inv_text)[:30]}...")

    print("="*115 + "\n")

if __name__ == "__main__":
    print_audit_table()
