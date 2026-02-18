import streamlit as st
import pandas as pd
import json
import re
from archive.legacy_streamlit.ui.common import render_tradingview_chart
from backend.engine.gemini import call_gemini_with_rotation, AVAILABLE_MODELS
from backend.engine.time_utils import now_et

def fetch_plan_safe(client_obj, ticker, full_context_mode=False):
    """Safe Fetch Function for Strategic Plans."""
    query = """
        SELECT cc.company_card_json, s.historical_level_notes 
        FROM company_cards cc
        JOIN stocks s ON cc.ticker = s.ticker
        WHERE cc.ticker = ? ORDER BY cc.date DESC LIMIT 1
    """
    try:
        rows = client_obj.execute(query, [ticker]).rows
        if rows and rows[0]:
            json_str, notes = rows[0][0], rows[0][1]
            card_data = json.loads(json_str) if json_str else {}
            if full_context_mode: return card_data
            return {
                "narrative_note": card_data.get('marketNote', 'N/A'),
                "strategic_bias": card_data.get('basicContext', {}).get('priceTrend', 'N/A'),
                "full_briefing": card_data.get('screener_briefing', 'N/A'),
                "key_levels_note": notes,
                "planned_support": card_data.get('technicalStructure', {}).get('majorSupport', 'N/A'),
                "planned_resistance": card_data.get('technicalStructure', {}).get('majorResistance', 'N/A')
            }
    except Exception as e: return e
    return "No Plan Found in DB"

def render_step_ranking(turso, db_url, auth_token, mode, simulation_cutoff_dt, simulation_cutoff_str):
    """Renders Step 3: Stock Ranking Tab."""
    st.header("Step 3: Head Trader Synthesis")
    if not st.session_state.glassbox_raw_cards:
        st.info("ℹ️ run 'Selection Hub (Step 2)' first to generate market data for ranking.")
        return

    available_tickers = sorted(list(st.session_state.glassbox_raw_cards.keys()))
    default_tickers = available_tickers[:3] if len(available_tickers) >= 3 else available_tickers
    if st.session_state.proximity_scan_results:
        prox_tickers = [x['Ticker'] for x in st.session_state.proximity_scan_results]
        valid_prox = [t for t in prox_tickers if t in available_tickers]
        if valid_prox: default_tickers = valid_prox

    with st.form(key='head_trader_controls'):
        st.markdown("### 🎛️ Strategic Parameters")
        selected_tickers = st.multiselect("Select Tickers", options=available_tickers, default=default_tickers)
        p1, p2 = st.columns(2)
        with p1: setup_type = st.selectbox("🎯 Setup Type", ["Any", "Gap & Go", "Reversal/Fade", "Breakout", "Dip Buy", "Range Bound"])
        with p2: confluence_mode = st.selectbox("🏗️ Confluence", ["Flexible", "Strict"])
        st.divider()
        layout_c1, layout_c2 = st.columns([1, 1])
        with layout_c1:
            model_labels = {"gemini-2.0-flash-exp": "Gemini 2.0 Flash (Fast)", "gemini-2.0-pro-exp-02-05": "Gemini 2.0 Pro (Deep)", "gemini-1.5-pro": "Gemini 1.5 Pro"}
            ht_model = st.selectbox("Head Trader Model", options=AVAILABLE_MODELS, index=0, format_func=lambda x: model_labels.get(x, x))
        with layout_c2:
            cb_c1, cb_c2 = st.columns(2)
            with cb_c1:
                prioritize_prox = st.checkbox("Prioritize Proximity", value=False)
                use_full_context = st.checkbox("📖 Use Full Context", value=False)
            with cb_c2:
                prioritize_rr = st.checkbox("Prioritize High R/R", value=False)
                dry_run_mode = st.checkbox("📋 Dry Run (Prompt Only)", value=False)
        submitted = st.form_submit_button("🧠 Run Head Trader Analysis", type="primary", width="stretch")

    if submitted:
        if not selected_tickers: st.error("Select at least one ticker.")
        else:
            macro_context = st.session_state.premarket_economy_card or st.session_state.glassbox_eod_card
            macro_summary = {"bias": macro_context.get('marketBias', 'Neutral'), "narrative": macro_context.get('marketNarrative', 'N/A'), "sector_rotation": macro_context.get('sectorRotation', {}), "key_action": macro_context.get('marketKeyAction', 'N/A')} if macro_context else "No Macro Context Available."

            strategic_plans = {}
            fetch_errors = [] 
            for tkr in selected_tickers:
                result = fetch_plan_safe(turso, tkr, use_full_context)
                if isinstance(result, Exception):
                    try: 
                        from libsql_client import create_client_sync
                        fresh_url = db_url.replace("libsql://", "https://")
                        if not fresh_url.startswith("https://"): fresh_url = f"https://{fresh_url}"
                        fresh_db = create_client_sync(url=fresh_url, auth_token=auth_token)
                        retry_res = fetch_plan_safe(fresh_db, tkr, use_full_context)
                        fresh_db.close()
                        if isinstance(retry_res, Exception): raise retry_res 
                        else: strategic_plans[tkr] = retry_res 
                    except Exception as final_e:
                        fetch_errors.append(f"{tkr}: {str(final_e)}")
                        strategic_plans[tkr] = "DATA FETCH FAILED" 
                else: strategic_plans[tkr] = result

            if fetch_errors:
                st.error("⚠️ DATA FETCH ERRORS DETECTED:")
                for err in fetch_errors: st.write(f"❌ {err}")

            context_packet = []
            for t in selected_tickers:
                card = st.session_state.glassbox_raw_cards[t]
                pm_migration = [b for b in card['value_migration_log'] if b['time_window'].split(' - ')[0].strip() < simulation_cutoff_dt.strftime('%H:%M')]
                context_packet.append({"ticker": t, "THE_ANCHOR (Strategic Plan)": strategic_plans.get(t, "No Plan Found"), "THE_DELTA (Live Tape)": {"current_price": card['reference_levels']['current_price'], "session_delta_structure": pm_migration, "new_impact_zones_detected": card['key_level_rejections']}})
            
            p1 = f"[ROLE]\nYou are Head Trader.\n[GLOBAL MACRO CONTEXT]\n{json.dumps(macro_summary, indent=2)}"
            chunks = [f"[CANDIDATE ANALYSIS - BATCH {i//3 + 1}]\n{json.dumps(context_packet[i:i+3], indent=2)}" for i in range(0, len(context_packet), 3)]
            p2_full = "\n".join(chunks)
            rr_i = "\n- **OVERRIDE: HIGH R/R**: YES." if prioritize_rr else ""
            prox_i = "\n- **OVERRIDE: PROXIMITY**: YES." if prioritize_prox else ""
            p3 = f"[TASK]\nRank Candidates. Return TOP 5 JSON LIST.\n**PARAMS**: setup={setup_type}, confluence={confluence_mode}{rr_i}{prox_i}\n[JSON SCHEMA]..."
            
            full_prompt = p1 + "\n" + p2_full + "\n" + p3
            st.session_state.ht_prompt_parts = {"p1": p1, "p2_chunks": chunks, "p3": p3, "full": full_prompt}
            st.session_state.ht_ready = True

            if not dry_run_mode:
                from backend.engine.utils import AppLogger
                log_expander = st.expander("📝 Live Execution Logs", expanded=True)
                ht_logger = AppLogger(log_expander.empty())
                with st.spinner(f"Head Trader Analyzing..."):
                    ht_resp, err = call_gemini_with_rotation(full_prompt, "You are a Head Trader.", ht_logger, ht_model, st.session_state.key_manager_instance)
                    if ht_resp:
                        try:
                            match = re.search(r"(\[[\s\S]*\])", ht_resp)
                            recommendations = json.loads(match.group(1)) if match else json.loads(ht_resp)
                            
                            st.markdown("### 🏆 Head Trader's Top 5")
                            
                            # CONVERGENCE CHECK LOGIC
                            macro_bias = macro_context.get('marketBias', 'Neutral').lower()
                            
                            for item in recommendations:
                                with st.container():
                                    st.subheader(f"#{item.get('rank')} {item.get('ticker')} ({item.get('direction')})")
                                    st.info(f"✅ **TRIGGER:** {item.get('trigger_condition')}")
                                    st.write(f"**Rationale:** {item.get('rationale')}")
                                    c1, c2, c3 = st.columns(3)
                                    p = item.get('plan', {})
                                    c1.metric("Entry", p.get('entry', 'N/A'))
                                    c2.metric("Stop", p.get('stop', 'N/A'))
                                    c3.metric("Target", p.get('target', 'N/A'))
                                    render_tradingview_chart(turso, item.get('ticker'), simulation_cutoff_str, mode=mode, trade_plan=p)
                                    st.divider()
                        except Exception as e:
                            st.warning("⚠️ AI Output Parse Error.")
                            st.markdown(ht_resp)
                    else: st.error(f"Head Trader Failed: {err}")

    if st.session_state.get("ht_ready"):
        st.success("✅ Prompt Generated!")
        with st.expander("📋 View AI Prompt"):
            st.code(st.session_state.ht_prompt_parts['full'], language="text")
