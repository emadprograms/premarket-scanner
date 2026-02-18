import streamlit as st
import json
import pandas as pd
from datetime import datetime
from backend.engine.database import get_db_connection, get_latest_economy_card_date, get_eod_economy_card
from backend.engine.analysis.macro_engine import generate_economy_card_prompt
from backend.engine.gemini import call_gemini_with_rotation
from backend.engine.key_manager import KeyManager
from backend.engine.utils import AppLogger, get_turso_credentials

# Page Config
st.set_page_config(page_title="Narrative Integrity Lab", page_icon="🧪", layout="wide")

st.title("🧪 Narrative Integrity Lab")
st.caption("Modular Stress-Testing for Anchor & Delta prompts. Mix-and-match scenarios to test AI reliability.")

# Initialize Logger
logger = AppLogger(None)

# 1. AUTH: SECURELY FETCH TURSO CREDENTIALS
db_url, auth_token = get_turso_credentials()
turso = get_db_connection(db_url, auth_token, local_mode=st.sidebar.checkbox("Local Mode", value=False))

if not turso:
    st.error("❌ Database Connection Failed. Please check Infisical secrets or network.")
    st.stop()

# Initialize Key Manager if missing
if 'key_manager_instance' not in st.session_state:
    st.session_state.key_manager_instance = KeyManager(db_url, auth_token)
km = st.session_state.key_manager_instance

# --- SIDEBAR: MISSION CONFIG ---
st.sidebar.header("Mission Config")
# Generate Display Labels from KeyManager
model_keys = list(KeyManager.MODELS_CONFIG.keys())
default_index = model_keys.index('gemini-3-flash-free') if 'gemini-3-flash-free' in model_keys else 0

selected_model_config_id = st.sidebar.selectbox(
    "Gemini Model", 
    options=model_keys, 
    format_func=lambda x: KeyManager.MODELS_CONFIG[x]['display'],
    index=default_index
)

# --- 1. THE ANCHOR: SELECT EOD CARD ---
st.header("1. The Anchor (Historical EOD Context)")
col_a1, col_a2 = st.columns([0.3, 0.7])

with col_a1:
    latest_date_str = get_latest_economy_card_date(turso, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), logger)
    default_date = datetime.strptime(latest_date_str, '%Y-%m-%d') if latest_date_str else datetime.now()
    selected_date = st.date_input("Select EOD Card Date", value=default_date)
    anchor_date_str = selected_date.strftime('%Y-%m-%d')

eod_card = {}
if anchor_date_str:
    eod_card = get_eod_economy_card(turso, anchor_date_str, logger)
    if eod_card:
        st.success(f"✅ Loaded EOD Card for {anchor_date_str}")
        with col_a2:
            with st.expander("View Anchor JSON", expanded=False):
                st.json(eod_card)
    else:
        st.error(f"❌ No EOD Card found for {anchor_date_str}.")

st.divider()

# --- 2. THE DELTA: MODULAR SCENARIOS ---
st.header("2. The Delta (Modular Stress-Test)")

# --- NEWS SCENARIOS (10) ---
NEWS_SCENARIOS = {
    "1. 🦅 Hawkish Fed Pivot": "BREAKING: Fed minutes reveal massive concern over sticky inflation. Several governors hint at 'High for Longer' and even a potential hike if data doesn't cooling. Yields spiking across the curve.",
    "2. 🚀 Earnings Explosion (Tech)": "Tech sector is roaring. Nvidia and Apple both smashed earnings expectations overnight, providing record-breaking 'AI Growth' guidance. Retail and Institutionals are chasing the gap up.",
    "3. 🕊️ Geopolitical De-escalation": "Major breakthrough in Eastern Europe peace negotiations. Ceasefire signed. Energy prices (Oil/Gas) are cratering -5%, removing significant inflation weight from the market.",
    "4. ⛽ Energy Supply Shock": "OPEC+ announces surprise additional 1M barrel cut. Brent Crude jumping to $95. Concerns over 'Cost-Push' inflation spreading through global markets.",
    "5. 📉 Goldilocks Jobs Data": "Non-Farm Payrolls come in slightly lower than expected, with cooling wage growth. Markets interpret this as the 'Perfect Soft Landing' scenario—inflation cooling without a recession.",
    "6. 🏦 Banking Liquidity Fear": "Regional bank earnings reveal a sharp drop in deposits. Contagion fears resurfacing. Market is rotation out of Risk and into Gold/Bonds.",
    "7. 🛒 Retail Spend Collapse": "Walmart and Target both report a major slowdown in discretionary spending. Consumer is tapped out. Fears of a hard economic landing rising.",
    "8. 😶 The Quiet Tape": "No major economic data releases. Overnight session was extremely low volume. No significant news headlines. Pure technical grind expected.",
    "9. 💣 Flash CPI Shock": "CPI data at 08:30am comes in 0.5% HIGHER than consensus. Core inflation is not moving. Market is immediately pricing in more aggressive hikes.",
    "10. 🐻 Recessionary Signals": "Industrial production and manufacturing data hit 3-year lows. Forward looking indicators suggest a deep contraction is beginning."
}

# --- STRUCTURAL SCENARIOS (10) ---
STRUCTURAL_SCENARIOS = {
    "1. 📈 Vertical Ascension": {
        "description": "Relentless buying from the 04:00 open. Price moves up in a straight line with high-volume acceptance and zero pullbacks. Suggests massive institutional conviction.",
        "data": [
            {
                "ticker": "SPY",
                "meta": {"pre_market_session_open": "04:00:00"},
                "reference_levels": {"current_price": 508.0, "yesterday_close": 500.0},
                "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Vertical lift, total acceptance into open sky"}}],
                "key_level_rejections": []
            }
        ]
    },
    "2. 🔄 V-Bottom Recovery": {
        "description": "Price initially collapsed at the open, hitting deep support. Buyers immediately stepped in, reclaiming the entire loss and pushing back to unchanged before the open.",
        "data": [
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
        ]
    },
    "3. 🌊 Waterfall Liquidation": {
        "description": "A catastrophic collapse where every support level is met with aggressive selling. Large red bars and a complete absence of bid-depth.",
        "data": [
            {
                "ticker": "SPY",
                "meta": {"pre_market_session_open": "04:00:00"},
                "reference_levels": {"current_price": 485.0, "yesterday_close": 500.0},
                "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Cascade liquidation, zero bids, breaking every local support"}}],
                "key_level_rejections": [{"type": "SUPPORT", "level": 495.0, "reason": "Screaming through support without a bounce."}]
            }
        ]
    },
    "4. 🌤️ The 'Open Sky' Gap": {
        "description": "Price gapped up significantly, bypassing all known resistance from the previous few days. Now in 'price discovery' mode with no overhead supply.",
        "data": [
            {
                "ticker": "SPY",
                "meta": {"pre_market_session_open": "04:00:00"},
                "reference_levels": {"current_price": 512.0, "yesterday_close": 500.0},
                "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Gapping over all local resistance, accepted in new price discovery zone"}}],
                "key_level_rejections": []
            }
        ]
    },
    "5. 🗜️ Tight Compression": {
        "description": "Price trapped in an extremely narrow range (<0.1%). Volume is thin and there is no directional intent. The Delta is essentially noise.",
        "data": [
            {
                "ticker": "SPY",
                "meta": {"pre_market_session_open": "04:00:00"},
                "reference_levels": {"current_price": 500.2, "yesterday_close": 500.0},
                "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Low volume chop, staying within +/- 0.1% range"}}],
                "key_level_rejections": []
            }
        ]
    },
    "6. 🚫 False Breakout (Bull Trap)": {
        "description": "Price initially surged higher, inviting longs. Heavy supply then entered, forcing price back into the range and trapping the breakout buyers.",
        "data": [
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
        ]
    },
    "7. 🏳️ Bull Flag Consolidation": {
        "description": "After a gap up, price moved sideways in an orderly channel. Refusal to give back gains suggests a 'rest' before the next leg up.",
        "data": [
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
        ]
    },
    "8. 🌪️ High Volume Shakeout": {
        "description": "Violent 1% swings both ways with long wicks. Clearing out stops before settling back at the open. Confusion reigns.",
        "data": [
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
        ]
    },
    "9. 🩸 The Slow Bleed": {
        "description": "Persistent, low-volume drift lower. Every minor bounce fails at a lower high. Suggests a lack of buying interest.",
        "data": [
            {
                "ticker": "SPY",
                "meta": {"pre_market_session_open": "04:00:00"},
                "reference_levels": {"current_price": 494.0, "yesterday_close": 500.0},
                "value_migration_log": [{"block_id": 1, "time_window": "04:00 - 07:00", "observations": {"price_action_nature": "Persistent low-volume drift lower, no bounce attempts"}}],
                "key_level_rejections": []
            }
        ]
    },
    "10. 🛡️ Retest & Defend": {
        "description": "Price pulled back to yesterday's POC/resistance. Level held perfectly as new support, and price bounced with conviction.",
        "data": [
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
}

col_sc1, col_sc2 = st.columns(2)

with col_sc1:
    selected_news_name = st.selectbox("Select News Delta (The Why)", options=list(NEWS_SCENARIOS.keys()))
    news_scen_text = NEWS_SCENARIOS[selected_news_name]
    st.info(f"📰 **News Scenario Detail:**\n\n{news_scen_text}")

with col_sc2:
    selected_struct_name = st.selectbox("Select Structural Delta (The What)", options=list(STRUCTURAL_SCENARIOS.keys()))
    struct_scen_desc = STRUCTURAL_SCENARIOS[selected_struct_name]["description"]
    struct_scen_data = STRUCTURAL_SCENARIOS[selected_struct_name]["data"]
    st.warning(f"📊 **Structural Behavior:**\n\n{struct_scen_desc}")
    with st.expander("View Structure JSON", expanded=False):
        st.json(struct_scen_data)

st.divider()

# --- 3. RUN TEST ---
st.header("3. Run Synthesis Test")
if st.button("🚀 Run Narrative Stress-Test", type="primary"):
    if not eod_card:
        st.error("Please select a valid Anchor Date first.")
        st.stop()

    with st.spinner(f"Synthesizing: Anchor ({anchor_date_str}) + Delta ({selected_news_name} & {selected_struct_name})..."):
        # Generate the Anchor & Delta Prompt
        prompt, system = generate_economy_card_prompt(
            eod_card=eod_card,
            etf_structures=struct_scen_data,
            news_input=news_scen_text,
            analysis_date_str=datetime.now().strftime("%Y-%m-%d"),
            logger=logger
        )
        
        # Call Gemini
        resp, err = call_gemini_with_rotation(
            prompt, 
            system, 
            logger, 
            selected_model_config_id, 
            km
        )
        
        if err:
            st.error(f"AI Error: {err}")
        else:
            st.header("🎯 Synthesis Result")
            try:
                # Cleanup markdown if present
                clean_json = resp.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:-3]
                elif clean_json.startswith("```"):
                    clean_json = clean_json[3:-3]
                
                result_json = json.loads(clean_json)
                
                # Narrative Nuance Mode
                narrative = result_json.get('marketNarrative', 'No narrative generated.')
                bias = result_json.get('marketBias', 'Neutral')
                
                st.markdown(f"### 📜 Market Narrative ({bias})")
                st.info(narrative)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### 📊 Index & Events")
                    st.json(result_json.get('indexAnalysis', {}))
                    st.json(result_json.get('keyEconomicEvents', {}))
                    
                with col2:
                    st.markdown("#### 🔄 Sector & Internals")
                    st.json(result_json.get('sectorRotation', {}))
                    st.json(result_json.get('marketInternals', {}))
                
                with st.expander("📝 View Full JSON", expanded=False):
                    st.json(result_json)
            except Exception as e:
                st.warning("Could not parse AI response as JSON. Displaying raw text.")
                st.write(resp)

        # Show the raw prompt for debugging
        # Show the raw prompt for debugging
        with st.expander("🔍 Review Full Prompt (The Glassbox)", expanded=False):
            st.code(f"SYSTEM:\n{system}\n\nUSER:\n{prompt}", language="text")
