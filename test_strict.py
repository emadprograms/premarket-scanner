import requests
import json

URL = "http://127.0.0.1:8000/api/scanner/scan"

PAYLOAD_STRICT = {
  "benchmark_date": "2026-02-18",
  "simulation_cutoff": "2026-02-18 20:30:00",
  "mode": "Live",
  "threshold": 2.5,
  "refresh_tickers": ["MU"],
  "plan_only": True
}

PAYLOAD_NORMAL = {
  "benchmark_date": "2026-02-18",
  "simulation_cutoff": "2026-02-18 20:30:00",
  "mode": "Live",
  "threshold": 2.5,
  "refresh_tickers": ["MU"],
  "plan_only": False
}

def run_test(name, payload):
    print(f"\n--- Testing {name} ---")
    try:
        r = requests.post(URL, json=payload, timeout=60)
        # Inspect metadata
        if r.status_code == 200:
            response_data = r.json()
            if response_data['status'] == 'success':
                res = next((x for x in response_data['data']['results'] if x['ticker'] == 'MU'), None)
                if res:
                    print(f"Prox Alert: {json.dumps(res.get('prox_alert'), indent=2)}")
                else:
                    print("MU result not found")

                coverage = response_data['data'].get('card_coverage', [])
                summary = response_data['data'].get('summary', {})
                print(f"Summary: {summary}")
                if coverage:
                    print(f"Coverage (first): {coverage[0]}")
            else:
                print(f"Failed: {response_data}")
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test strict mode first
    run_test("STRICT MODE (Expect Plan Only or None)", PAYLOAD_STRICT)
    # Test normal mode
    run_test("NORMAL MODE (Expect Key Level Alert)", PAYLOAD_NORMAL)
