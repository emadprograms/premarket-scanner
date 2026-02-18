import requests
import json

URL = "http://127.0.0.1:8000/api/scanner/scan"

def run_test(name, plan_only):
    print(f"\n--- Testing {name} ---")
    payload = {
        "benchmark_date": "2024-05-13",
        "simulation_cutoff": "2024-05-13 14:00:00",
        "refresh_tickers": ["MU"],
        "threshold": 3.0,
        "mode": "Live",
        "plan_only_proximity": plan_only
    }
    # Manually restrict tickers in the mock watchlist for speed? 
    # Or just let it run if the watchlist is short. 
    # Wait, the watchlist is fetched from Turso. I can't easily restrict it here.
    
    try:
        r = requests.post(URL, json=payload, timeout=60)
        if r.status_code == 200:
            data = r.json()
            coverage = data['data'].get('card_coverage', [])
            summary = data['data'].get('summary', {})
            print(f"Summary: {summary}")
            if coverage:
                # Show first few results
                for c in coverage[:3]:
                    print(f"Ticker: {c['ticker']} | Blocks: {c['migration_blocks']} | Source: {c['source']}")
                
                # Check for MU specifically
                mu = next((c for c in coverage if c['ticker'] == 'MU'), None)
                if mu:
                    print(f"MU Metadata: {mu}")
            
            results = data['data'].get('results', [])
            mu_res = next((x for x in results if x['ticker'] == 'MU'), None)
            if mu_res:
                print(f"MU Prox Alert (with Bias): {json.dumps(mu_res.get('prox_alert'), indent=2)}")
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

run_test("STRICT MODE", True)
run_test("NORMAL MODE", False)
