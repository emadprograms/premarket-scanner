import os
import sys
import json
import pandas as pd
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.database import get_db_connection, get_latest_economy_card_date, get_eod_economy_card
from modules.analysis.macro_engine import generate_economy_card_prompt
from modules.gemini import call_gemini_with_rotation
from modules.key_manager import KeyManager
from modules.utils import AppLogger, get_turso_credentials

# Scenario Definitions (Copied from app.py)
NEWS_SCENARIOS = {
    "1. Hawkish Fed Pivot": "BREAKING: Fed minutes reveal massive concern over sticky inflation. Several governors hint at 'High for Longer' and even a potential hike if data doesn't cooling. Yields spiking across the curve.",
    "2. Tech Earnings Explosion": "Tech sector is roaring. Nvidia and Apple both smashed earnings expectations overnight, providing record-breaking 'AI Growth' guidance. Retail and Institutionals are chasing the gap up.",
    "3. Geopolitical De-escalation": "Major breakthrough in Eastern Europe peace negotiations. Ceasefire signed. Energy prices (Oil/Gas) are cratering -5%, removing significant inflation weight from the market.",
    "4. Energy Supply Shock": "OPEC+ announces surprise additional 1M barrel cut. Brent Crude jumping to $95. Concerns over 'Cost-Push' inflation spreading through global markets.",
    "5. Goldilocks Jobs": "Non-Farm Payrolls come in slightly lower than expected, with cooling wage growth. Markets interpret this as the 'Perfect Soft Landing' scenario—inflation cooling without a recession.",
    "6. Banking Liquidity Fear": "Regional bank earnings reveal a sharp drop in deposits. Contagion fears resurfacing. Market is rotation out of Risk and into Gold/Bonds.",
    "7. Retail Spend Collapse": "Walmart and Target both report a major slowdown in discretionary spending. Consumer is tapped out. Fears of a hard economic landing rising.",
    "8. The Quiet Tape": "No major economic data releases. Overnight session was extremely low volume. No significant news headlines. Pure technical grind expected.",
    "9. Flash CPI Shock": "CPI data at 08:30am comes in 0.5% HIGHER than consensus. Core inflation is not moving. Market is immediately pricing in more aggressive hikes.",
    "10. Recessionary Signals": "Industrial production and manufacturing data hit 3-year lows. Forward looking indicators suggest a deep contraction is beginning."
}

STRUCTURAL_SCENARIOS = {
    "1. Vertical Ascension": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 508.0, "yesterday_close": 500.0},
            "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Vertical lift, total acceptance into open sky"}}],
            "key_level_rejections": []
        }
    ],
    "2. V-Bottom Recovery": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 500.2, "yesterday_close": 500.0},
            "value_migration_log": [
                {"block_id": 1, "time_window": "04:00 - 05:00", "observations": {"price_action_nature": "Violent sell-off to 495"}},
                {"block_id": 2, "time_window": "05:00 - 07:00", "observations": {"price_action_nature": "V-Recovery, reclaimed all losses, accepted at POC"}}
            ],
            "key_level_rejections": [{"type": "SUPPORT", "level": 495.0, "reason": "Hard bounce at major demand zone."}]
        }
    ],
    "3. Waterfall Liquidation": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 485.0, "yesterday_close": 500.0},
            "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Cascade liquidation, zero bids, breaking every local support"}}],
            "key_level_rejections": [{"type": "SUPPORT", "level": 495.0, "reason": "Screaming through support without a bounce."}]
        }
    ],
    "4. Open Sky Gap": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 512.0, "yesterday_close": 500.0},
            "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Gapping over all local resistance, accepted in new price discovery zone"}}],
            "key_level_rejections": []
        }
    ],
    "5. Tight Compression": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 500.2, "yesterday_close": 500.0},
            "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Low volume chop, staying within +/- 0.1% range"}}],
            "key_level_rejections": []
        }
    ],
    "6. Bull Trap": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 498.0, "yesterday_close": 500.0},
            "value_migration_log": [
                {"block_id": 1, "time_window": "04:00 - 05:00", "observations": {"price_action_nature": "Initially lifted to 505"}},
                {"block_id": 2, "time_window": "05:00 - 07:00", "observations": {"price_action_nature": "Failed rejection, collapsed back below open"}}
            ],
            "key_level_rejections": [{"type": "RESISTANCE", "level": 505.0, "reason": "Trapped bulls, heavy selling at the high."}]
        }
    ],
    "7. Bull Flag": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 506.0, "yesterday_close": 500.0},
            "value_migration_log": [
                {"block_id": 1, "time_window": "04:00 - 04:30", "observations": {"price_action_nature": "Initial gap up to 507"}},
                {"block_id": 2, "time_window": "04:30 - 07:00", "observations": {"price_action_nature": "Tight flag formation, refusing to pull back"}}
            ],
            "key_level_rejections": []
        }
    ],
    "8. High Volume Shakeout": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 500.0, "yesterday_close": 500.0},
            "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Violent 1% swings both ways, clearing out stops before settling at unchanged"}}],
            "key_level_rejections": [
                {"type": "RESISTANCE", "level": 505.0, "reason": "Wick rejection."},
                {"type": "SUPPORT", "level": 495.0, "reason": "Wick rejection."}
            ]
        }
    ],
    "9. Slow Bleed": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 494.0, "yesterday_close": 500.0},
            "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Persistent low-volume drift lower, no bounce attempts"}}],
            "key_level_rejections": []
        }
    ],
    "10. Retest & Defend": [
        {
            "ticker": "SPY",
            "meta": {"pre_market_session_open": "04:00:00"},
            "reference_levels": {"current_price": 502.0, "yesterday_close": 500.0},
            "value_migration_log": [
                {"block_id": 1, "time_window": "04:00 - 05:00", "observations": {"price_action_nature": "Dipped to yesterday's POC at 498"}},
                {"block_id": 2, "time_window": "05:00 - 07:00", "observations": {"price_action_nature": "Buyers stepped in strong to defend the breakout level"}}
            ],
            "key_level_rejections": [{"type": "SUPPORT", "level": 498.0, "reason": "Perfect retest of former resistance."}]
        }
    ]
}

def run_evaluation():
    logger = AppLogger(None)
    # Hardcoded for stability in background execution
    db_url = "https://analyst-workbench-database-emadarshadalam.aws-ap-south-1.turso.io"
    auth_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NjI1MjIwMDMsImlkIjoiMTA5NjAzY2QtYzhkZi00OTE3LWIwZTItMDgzNjFmMjFkZTUwIiwicmlkIjoiZjcxOTdhOTgtYjViZS00NmY3LTk2YmQtMWNjZjNlYTRlMWQ5In0.hU4LWQ43wbsptdK_KLF7je8RxoCKgZ20WJL5aOMpcV4NbnnQhIYe60rBGoQJzTXiIhDEoCas9Ai7LuybrhCPCQ"
    turso = get_db_connection(db_url, auth_token, local_mode=False)
    
    if not turso:
        print("❌ DB Connection Failed")
        return

    km = KeyManager(db_url, auth_token)
    model_id = 'gemini-3-flash-free'
    
    latest_date_str = get_latest_economy_card_date(turso, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), logger)
    eod_card = get_eod_economy_card(turso, latest_date_str, logger)
    
    if not eod_card:
        print("❌ No Anchor Card found")
        return

    # Load existing results if they exist in the same folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_file = os.path.join(script_dir, "narrative_evaluation_results.json")
    
    results = []
    if os.path.exists(results_file):
        with open(results_file, "r") as f:
            results = json.load(f)
    
    # Map of already finished combinations
    finished = set()
    for r in results:
        if r.get("Bias") != "Error":
            finished.add((r["News_Scenario"], r["Structural_Scenario"]))

    total_scenarios = len(NEWS_SCENARIOS) * len(STRUCTURAL_SCENARIOS)
    to_run = []
    for n_name, news in NEWS_SCENARIOS.items():
        for s_name, struct in STRUCTURAL_SCENARIOS.items():
            if (n_name, s_name) not in finished:
                to_run.append((n_name, news, s_name, struct))

    if not to_run:
        print("✅ All 100 scenarios already completed.")
        return

    print(f"--- Re-running {len(to_run)}/{total_scenarios} Scenarios in Parallel ---")
    
    import concurrent.futures
    import time
    from threading import Lock

    report_lock = Lock()
    count = 0

    def evaluate_combination(n_name, news, s_name, struct):
        nonlocal count
        prompt, system = generate_economy_card_prompt(
            eod_card=eod_card,
            etf_structures=struct,
            news_input=news,
            analysis_date_str=datetime.now().strftime("%Y-%m-%d"),
            logger=logger
        )
        
        # Multi-Model Failover Strategy
        model_tier_list = ['gemini-3-flash-free', 'gemini-2.5-flash-free', 'gemini-2.5-flash-lite-free']
        resp, err = None, None
        
        for m_id in model_tier_list:
            for attempt in range(2):
                print(f"   -> Trying {m_id} (Attempt {attempt+1})")
                resp, err = call_gemini_with_rotation(prompt, system, logger, m_id, km)
                if resp: break
                time.sleep(10)
            if resp: break
            print(f"   ⚠️ {m_id} Failed. Trying next model...")
        
        bias, narrative = "Error", f"Error: {err}" if err else "Error: Unknown"
        if resp:
            try:
                clean = resp.strip()
                if "```json" in clean: clean = clean.split("```json")[1].split("```")[0].strip()
                data = json.loads(clean)
                bias = data.get('marketBias', 'N/A')
                narrative = data.get('marketNarrative', 'N/A')
            except: 
                bias = "JSON Error"
                narrative = resp[:500]

        with report_lock:
            count += 1
            print(f"[{count}/{len(to_run)}] Finished: {n_name} + {s_name} | Bias: {bias}")
            if err and bias == "Error":
                print(f"   ⚠️ Error Details: {err[:200]}...")
            
            # Update results (find and replace or append)
            updated = False
            for r in results:
                if r["News_Scenario"] == n_name and r["Structural_Scenario"] == s_name:
                    r["Bias"] = bias
                    r["Narrative"] = narrative
                    updated = True
                    break
            if not updated:
                results.append({
                    "News_Scenario": n_name,
                    "Structural_Scenario": s_name,
                    "Bias": bias,
                    "Narrative": narrative
                })
            
            # Incremental save
            with open(results_file, "w") as f:
                json.dump(results, f, indent=2)

    # Use a single worker for maximum stability
    print(f"--- Processing {len(to_run)} Scenarios Sequentially (20s delay) ---")
    
    for combo in to_run:
        evaluate_combination(*combo)
        time.sleep(20) # Conservative backoff to ensure rate limits clear

    print("\n✅ Evaluation Complete. Results finalized in narrative_evaluation_results.json")

if __name__ == "__main__":
    run_evaluation()
