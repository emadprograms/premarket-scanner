import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render_mission_config(available_models, formatter=None):
    # 1. Reserve Top Space for Status
    status_container = st.container()

    # 2. Render Config (Standard Flow)
    with st.expander("⚙️ Mission Config", expanded=True):
        # Fallback Init for Subpages
        import pytz
        if 'market_timezone' not in st.session_state:
             st.session_state.market_timezone = pytz.timezone('US/Eastern')
        
        st.caption("🟢 System Ready (v3.1 Verified)")
        
        # Row 1: Model, Mode, Time
        c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
        
        with c1:
            format_func = (lambda x: formatter.get(x, x)) if formatter else (lambda x: x)
            selected_model = st.selectbox("AI Model", available_models, index=0, label_visibility="collapsed", format_func=format_func)
        
        with c2:
            # Toggle is cleaner than radio
            is_sim = st.toggle("Sim Mode", value=False) 
            logic_mode = "Simulation" if is_sim else "Live"

        with c3:
            # NEW: Local Test Mode Toggle
            is_local = st.toggle("🛰️ Local", value=False, help="Use local database cache to save Turso reads.")
            st.session_state.local_mode = is_local

        with c4:
            if logic_mode == "Live":
                simulation_cutoff_dt = datetime.now(st.session_state.market_timezone)
                st.caption(f"🟢 **LIVE**: {simulation_cutoff_dt.strftime('%H:%M:%S')} ET")
            else:
                # Simulation Mode - Compact Date/Time
                sc1, sc2 = st.columns(2)
                with sc1:
                    sim_date = st.date_input("Date", label_visibility="collapsed")
                with sc2:
                    sim_time = st.time_input("Time (ET)", value=datetime.strptime("09:26", "%H:%M").time(), step=120, label_visibility="collapsed")
                
                # FIX: Use localize for pytz timezones to handle DST/Offset correctly
                naive_dt = datetime.combine(sim_date, sim_time)
                simulation_cutoff_dt = st.session_state.market_timezone.localize(naive_dt)

        # NEW: Sync Button Area
        if is_local:
            st.divider()
            sc1, sc2 = st.columns([1, 2])
            with sc1:
                if st.button("🔄 Sync Database", use_container_width=True):
                    # We will handle the actual sync logic in app.py via callback/return
                    st.session_state.trigger_sync = True
            with sc2:
                import os
                if os.path.exists("local_cache.db"):
                    mtime = os.path.getmtime("local_cache.db")
                    last_sync = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    st.caption(f"Last Sync: {last_sync}")
                else:
                    st.warning("No local cache found. Please Sync.")

        # FIX: Database stores timestamps in UTC.
        # We must convert the ET cutoff to UTC for the SQL query string.
        cutoff_utc = simulation_cutoff_dt.astimezone(pytz.utc)
        simulation_cutoff_str = cutoff_utc.strftime('%Y-%m-%d %H:%M:%S')
        
        analysis_date = sim_date if logic_mode == "Simulation" else simulation_cutoff_dt.date()
        st.session_state.analysis_date = analysis_date

    # 3. Populate Status Container (Appears at TOP)
    with status_container:
        s1, s2, s3 = st.columns(3)
        s1.caption(f"📅 Analysis: **{analysis_date}**")
        
        # NEW: Show Strategic Plan (EOD Card) Date
        plan_date = st.session_state.get('glassbox_eod_date', 'None')
        s1.caption(f"📜 Strategic Plan: **{plan_date}**")
        
        if 'key_manager_instance' in st.session_state and st.session_state.key_manager_instance:
                s2.success("✅ Key Manager: Active")
        else:
                s2.error("❌ Key Manager: Failed")
                
        # Assuming if we are here, DB is connected (app.py checks it)
        s3.success("✅ Database: Connected")
        st.divider() # Divider below status, above Config

    return selected_model, logic_mode, simulation_cutoff_dt, simulation_cutoff_str

def render_main_content(mode, simulation_cutoff_dt):
    st.header("Step 1: Macro Context")
    pm_news = st.text_area("News Input", height=100, key="pm_news_input")
    
    st.markdown("---")
    return pm_news

def render_proximity_scan():
    # Header handled in Context_Engine.py

    pct_threshold = st.slider("Proximity %", 0.1, 5.0, 2.5)
    if st.button("Run Proximity Scan"):
        if not st.session_state.latest_macro_date:
            st.error("Generate Macro Card first.")
            st.stop()
        return pct_threshold
    return None

def render_battle_commander():
    st.header("Step 3: Head Trader Synthesis")
    return None