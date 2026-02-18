import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from datetime import datetime, timezone
import pytz
from streamlit_lightweight_charts import renderLightweightCharts

# ==============================================================================
# HELPER: VISUALIZE STRUCTURE FOR USER
# ==============================================================================
def escape_markdown(text):
    """Escapes special Markdown characters in a string for safe rendering."""
    if not isinstance(text, str):
        return text
    # Escape $ and ~
    return text.replace('$', '\\$').replace('~', '\\~')

# ==============================================================================
# AUDIT LOGGER
# ==============================================================================
class AuditLogger:
    """Helper to capture internal API logs into Streamlit Session State for persistence."""
    def __init__(self, session_state_key: str):
        self.key = session_state_key
        self.error_key = f"{session_state_key}_has_errors"
        if self.error_key not in st.session_state:
            st.session_state[self.error_key] = False

    def log(self, message: str):
        if self.key in st.session_state:
            st.session_state[self.key].append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        if "❌" in message or "Worker Error" in message or "Failed" in message:
            st.session_state[self.error_key] = True
        print(message)

# ==============================================================================
# MISSION CONFIGURATION (Moved from archive.legacy_streamlit.ui.py)
# ==============================================================================
# ==============================================================================
# MISSION CONFIGURATION (Moved from archive.legacy_streamlit.ui.py)
# ==============================================================================
def render_mission_config(available_models, formatter=None):
    # 1. Reserve Top Space for Status
    status_container = st.container()

    # 2. Render Config (Standard Flow)
    with st.expander("⚙️ Mission Config", expanded=True):
        # Fallback Init for Subpages
        if 'market_timezone' not in st.session_state:
             st.session_state.market_timezone = pytz.timezone('US/Eastern')
        
        st.caption("🟢 System Ready (v3.1 Verified)")
        
        # Row 1: Model, Mode, Time
        c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
        
        with c1:
            format_func = (lambda x: formatter.get(x, x)) if formatter else (lambda x: x)
            selected_model = st.selectbox("AI Model", available_models, index=0, label_visibility="collapsed", format_func=format_func)
        
        with c2:
            is_sim = st.toggle("Sim Mode", value=False) 
            logic_mode = "Simulation" if is_sim else "Live"

        with c3:
            is_local = st.toggle("🛰️ Local", value=False, help="Use local database cache to save Turso reads.")
            st.session_state.local_mode = is_local

        with c4:
            if logic_mode == "Live":
                simulation_cutoff_dt = datetime.now(st.session_state.market_timezone)
                st.caption(f"🟢 **LIVE**: {simulation_cutoff_dt.strftime('%H:%M:%S')} ET")
                st.session_state.db_fallback = st.toggle("DB Fallback", value=False, help="If Live API fails, try reading from Turso DB.")
            else:
                st.session_state.db_fallback = False
                sc1, sc2 = st.columns(2)
                with sc1:
                    sim_date = st.date_input("Date", label_visibility="collapsed")
                with sc2:
                    sim_time = st.time_input("Time (ET)", value=datetime.strptime("09:26", "%H:%M").time(), step=120, label_visibility="collapsed")
                
                # Use time_utils logic here if possible, but keeping it simple for now
                naive_dt = datetime.combine(sim_date, sim_time)
                simulation_cutoff_dt = st.session_state.market_timezone.localize(naive_dt)

        if is_local:
            st.divider()
            sc1, sc2 = st.columns([1, 2])
            with sc1:
                if st.button("🔄 Sync Database", use_container_width=True):
                    st.session_state.trigger_sync = True
            with sc2:
                import os
                if os.path.exists("data/local_turso.db"):
                    mtime = os.path.getmtime("data/local_turso.db")
                    last_sync = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    st.caption(f"Last Sync: {last_sync}")
                else:
                    st.warning("No local cache found. Please Sync.")

        cutoff_utc = simulation_cutoff_dt.astimezone(pytz.utc)
        simulation_cutoff_str = cutoff_utc.strftime('%Y-%m-%d %H:%M:%S')
        
        analysis_date = sim_date if logic_mode == "Simulation" else simulation_cutoff_dt.date()
        st.session_state.analysis_date = analysis_date

    # 3. Populate Status Container (Appears at TOP)
    with status_container:
        s1, s2, s3 = st.columns(3)
        s1.caption(f"📅 Analysis: **{analysis_date}**")
        plan_date = st.session_state.get('glassbox_eod_date', 'None')
        s1.caption(f"📜 Strategic Plan: **{plan_date}**")
        
        if 'key_manager_instance' in st.session_state and st.session_state.key_manager_instance:
                s2.success("✅ Key Manager: Active")
        else:
                s2.error("❌ Key Manager: Failed")
        s3.success("✅ Database: Connected")
        st.divider()

    return selected_model, logic_mode, simulation_cutoff_dt, simulation_cutoff_str

# ==============================================================================
# VIEW: ECONOMY CARD
# ==============================================================================
def display_view_economy_card(card_data, key_prefix="eco_view", edit_mode_key="edit_mode_economy"):
    """Displays the Economy card data in a read-only, formatted Markdown view."""
    data = card_data
    
    with st.expander("🌍 Global Economy Narrative", expanded=True):
        title_col, button_col = st.columns([0.9, 0.1])
        with title_col:
            st.markdown(f"### {escape_markdown(data.get('marketNarrative', 'Initializing Narrative...'))}")
        
        with button_col:
            def _enter_econ_edit_mode():
                st.session_state[edit_mode_key] = True
                try: st.rerun()
                except: pass
            st.button("✏️", key=f"{key_prefix}_edit_narrative", help="Edit narrative", on_click=_enter_econ_edit_mode)

        st.markdown(f"**Market Bias:** {escape_markdown(data.get('marketBias', 'N/A'))}")
        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            with st.container():
                st.markdown("##### Key Economic Events")
                events = data.get("keyEconomicEvents", {})
                st.markdown("**Last 24h:**")
                st.info(escape_markdown(events.get('last_24h', 'N/A')))
                st.markdown("**Next 24h:**")
                st.warning(escape_markdown(events.get('next_24h', 'N/A')))

            with st.container():
                st.markdown("##### Index Analysis")
                indices = data.get("indexAnalysis", {})
                st.markdown(f"**Pattern:** {escape_markdown(indices.get('pattern', 'N/A'))}")
                for index, analysis in indices.items():
                    if index != 'pattern' and analysis and analysis.strip():
                        st.markdown(f"**{index}:** {escape_markdown(analysis)}")

        with col2:
            with st.container():
                st.markdown("##### Sector Rotation")
                rotation = data.get("sectorRotation", {})
                st.markdown(f"**Leading:** {escape_markdown(', '.join(rotation.get('leadingSectors', [])) or 'N/A')}")
                st.markdown(f"**Lagging:** {escape_markdown(', '.join(rotation.get('laggingSectors', [])) or 'N/A')}")
                st.write(escape_markdown(rotation.get('rotationAnalysis', 'N/A')))

            with st.container():
                st.markdown("##### Inter-Market Analysis")
                intermarket = data.get("interMarketAnalysis", {})
                for asset, analysis in intermarket.items():
                    if analysis and analysis.strip():
                        st.markdown(f"**{asset.replace('_', ' ')}**")
                        st.write(escape_markdown(analysis))

            with st.container():
                st.markdown("##### Market Internals")
                internals = data.get("marketInternals", {})
                for key, analysis in internals.items():
                    if analysis and analysis.strip():
                        st.markdown(f"**{key.capitalize()}:**")
                        st.write(escape_markdown(analysis))

        st.markdown("---")
        st.markdown("##### Market Key Action Log")
        key_log = data.get('keyActionLog', [])
        if isinstance(key_log, list) and key_log:
            with st.expander("Show Full Market Action Log..."):
                for entry in reversed(key_log): 
                    if isinstance(entry, dict):
                        st.markdown(f"**{entry.get('date', 'N/A')}:** {escape_markdown(entry.get('action', 'N/A'))}")
        
        st.write(f"*Note: {data.get('todaysAction', 'No summary available.')}*")

# ==============================================================================
# VISUALIZATION: MARKET STRUCTURE (PLOTLY)
# ==============================================================================
def render_market_structure_chart(card_data, trade_plan=None):
    """Visualizes the raw JSON data sent to the AI (30m Blocks)."""
    try:
        if isinstance(card_data, str):
            card_data = json.loads(card_data)
        
        ticker = card_data.get('meta', {}).get('ticker', 'Unknown')
        blocks = card_data.get('value_migration_log', [])
        if not blocks: return None
        
        x_vals = []
        highs = []
        lows = []
        pocs = []
        hover_texts = []
        
        for b in blocks:
            obs = b.get('observations', {})
            x_vals.append(b.get('time_window', f"Block {b.get('block_id')}"))
            highs.append(obs.get('block_high'))
            lows.append(obs.get('block_low'))
            pocs.append(obs.get('most_traded_price_level'))
            hover_attrs = [f"{k}: {v}" for k,v in obs.items() if k != 'price_action_nature']
            hover_texts.append("<br>".join(hover_attrs))

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=x_vals, y=[h-l for h,l in zip(highs, lows)], base=lows,
            marker_color='rgba(100, 149, 237, 0.6)', name='Block Range', hoverinfo='skip'
        ))
        fig.add_trace(go.Scatter(
            x=x_vals, y=pocs, mode='lines+markers',
            marker=dict(size=8, color='#00CC96'), line=dict(color='#00CC96', width=2),
            name='POC Migration', text=hover_texts
        ))
        rejections = card_data.get('key_level_rejections', [])
        for r in rejections:
            color = '#FF4136' if r['type'] == 'RESISTANCE' else '#0074D9'
            fig.add_hline(y=r['level'], line_dash="dot", line_color=color, annotation_text=r['type'])

        fig.update_layout(
            title=f"{ticker} Market Structure (30m Blocks)", height=400, template="plotly_dark",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        return fig
    except Exception:
        return None

# ==============================================================================
# VISUALIZATION: TRADINGVIEW (LIGHTWEIGHT)
# ==============================================================================
def render_tradingview_chart(turso_client, ticker, cutoff_str, mode="Simulation", trade_plan=None):
    """Renders an interactive TradingView-style chart using Turso DB OR Capital.com."""
    from backend.engine.processing import get_historical_bars_for_chart
    try:
        df = get_historical_bars_for_chart(turso_client, ticker, cutoff_str, days=5, mode=mode)
        if df is None or df.empty: return None
        df = df.tail(150)
        
        candles = []
        for _, row in df.iterrows():
            ts = int(row['timestamp'].timestamp())
            candles.append({
                "time": ts,
                "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close']
            })

        series = [{"type": "Candlestick", "data": candles, "options": {"upColor": "#26a69a", "downColor": "#ef5350", "borderVisible": False, "wickUpColor": "#26a69a", "wickDownColor": "#ef5350"}}]
        
        if trade_plan:
            try:
                plan_norm = {k.lower(): v for k,v in trade_plan.items()}
                def safe_float(val):
                    if isinstance(val, (int, float)): return float(val)
                    if isinstance(val, str): return float(val.replace('$','').replace(',','').strip())
                    return None
                entry = safe_float(plan_norm.get('entry'))
                stop = safe_float(plan_norm.get('stop'))
                target = safe_float(plan_norm.get('target'))
                
                if entry:
                    series.append({"type": "Line", "data": [{"time": c["time"], "value": entry} for c in candles], "options": {"color": "#FFEB3B", "lineWidth": 2, "lineStyle": 2, "priceLineVisible": False, "lastValueVisible": False, "title": "ENTRY"}})
                if stop:
                    series.append({"type": "Line", "data": [{"time": c["time"], "value": stop} for c in candles], "options": {"color": "#FF1744", "lineWidth": 2, "priceLineVisible": False, "lastValueVisible": False, "title": "STOP"}})
                if target:
                    series.append({"type": "Line", "data": [{"time": c["time"], "value": target} for c in candles], "options": {"color": "#00E676", "lineWidth": 2, "priceLineVisible": False, "lastValueVisible": False, "title": "TARGET"}})
                if entry and target:
                    last_c = candles[-1]; last_ts = last_c['time']; curr_price = last_c['close']
                    ts_entry = last_ts + 3600; ts_target = last_ts + 10800
                    series.append({"type": "Line", "data": [{"time": last_ts, "value": curr_price}, {"time": ts_entry, "value": entry}], "options": {"color": "cyan", "lineWidth": 2, "lineStyle": 2, "title": "", "crosshairMarkerVisible": False, "priceLineVisible": False, "lastValueVisible": False}, "markers": [{"time": ts_entry, "position": "aboveBar" if entry < curr_price else "belowBar", "color": "cyan", "shape": "arrowDown" if entry < curr_price else "arrowUp", "size": 2}]})
                    series.append({"type": "Line", "data": [{"time": ts_entry, "value": entry}, {"time": ts_target, "value": target}], "options": {"color": "cyan", "lineWidth": 2, "lineStyle": 0, "title": "", "crosshairMarkerVisible": False, "priceLineVisible": False, "lastValueVisible": False}, "markers": [{"time": ts_target, "position": "aboveBar" if target < entry else "belowBar", "color": "cyan", "shape": "arrowDown" if target < entry else "arrowUp", "size": 2}]})
            except Exception as e: print(f"Overlay Error: {e}")

        chartOptions = {"layout": {"textColor": "#d1d4dc", "background": {"type": "solid", "color": "#0E1117"}}, "grid": {"vertLines": {"color": "rgba(42, 46, 57, 0.5)"}, "horzLines": {"color": "rgba(42, 46, 57, 0.5)"}}, "height": 500, "rightPriceScale": {"scaleMargins": {"top": 0.1, "bottom": 0.1}, "borderColor": "rgba(197, 203, 206, 0.8)"}, "timeScale": {"borderColor": "rgba(197, 203, 206, 0.8)", "timeVisible": True, "secondsVisible": False}}
        st.subheader(f"📊 {ticker} (5m Interactive)")
        renderLightweightCharts([{"chart": chartOptions, "series": series}], key=f"ht_chart_{ticker}")
        return True
    except Exception as e:
        st.error(f"Chart Error ({ticker}): {e}")
        return None

# ==============================================================================
# VISUALIZATION: SIMPLE LIGHTWEIGHT CHART
# ==============================================================================
def render_lightweight_chart_simple(df, ticker, height=300):
    """Renders a simple interactive candlestick chart from a DataFrame."""
    try:
        if df is None or df.empty: 
            st.warning(f"No Data for {ticker}")
            return
        df_norm = df.copy()
        df_norm.columns = [c.lower() for c in df_norm.columns]
        if 'timestamp' not in df_norm.columns:
             if isinstance(df.index, pd.DatetimeIndex): df_norm['timestamp'] = df.index
             else: return
        df_norm['timestamp'] = pd.to_datetime(df_norm['timestamp'])
        df_norm.dropna(subset=['timestamp', 'open', 'high', 'low', 'close'], inplace=True)
        df_norm.sort_values('timestamp', inplace=True)
        df_norm.drop_duplicates(subset='timestamp', keep='last', inplace=True)
        if df_norm.empty: return
        candles = []
        for _, row in df_norm.iterrows():
            ts = int(row['timestamp'].timestamp())
            if pd.isna(row['open']): continue
            candles.append({"time": ts, "open": row.get('open', 0), "high": row.get('high', 0), "low": row.get('low', 0), "close": row.get('close', 0)})
        series = [{"type": "Candlestick", "data": candles, "options": {"upColor": "#26a69a", "downColor": "#ef5350", "borderVisible": False, "wickUpColor": "#26a69a", "wickDownColor": "#ef5350"}}]
        chart_options = {"layout": {"textColor": "#d1d4dc", "background": {"type": "solid", "color": "#131722"}}, "grid": {"vertLines": {"color": "rgba(42, 46, 57, 0.5)"}, "horzLines": {"color": "rgba(42, 46, 57, 0.5)"}}, "height": height, "timeScale": { "timeVisible": True, "secondsVisible": False }}
        safe_ticker = ticker.replace("=", "_").replace("^", "").replace(".", "_")
        renderLightweightCharts([{"chart": chart_options, "series": series}], key=f"lc_{safe_ticker}")
    except Exception as e:
        st.error(f"Chart Render Error ({ticker}): {e}")
