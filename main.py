import streamlit as st
from src.config.constants import CORE_INTERMARKET_EPICS
from src.config.credentials import load_gemini_keys
from src.logging.app_logger import AppLogger

from src.workflows.generate_macro_card import generate_premarket_economy_card
from src.workflows.find_in_play_stocks import run_proximity_scan
from src.workflows.rank_trade_setups import run_head_trader_screener

# === Session State Init ===
for key, default in [
    ("capital_session", {"cst": None, "xst": None}),
    ("premarket_economy_card", None),
    ("latest_macro_date", None),
    ("proximity_scan_results", []),
    ("curated_tickers_for_screener", []),
    ("premarket_screener_output", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

st.set_page_config(page_title="Pre-Market Analyst", layout="wide")
st.title("Pre-Market Analyst Workbench")

# === Authentication (Step 0) ===
if not st.session_state.capital_session.get("cst"):
    st.warning("You must be logged in to Capital.com.")
    auth_logs = st.expander("Authentication Logs", True)
    auth_logger = AppLogger(auth_logs, log_key="auth")

    if st.button("Create Capital.com Session", use_container_width=True):
        auth_logger.clear()
        from src.external_services.broker_api.authentication import create_capital_session
        cst, xst = create_capital_session(auth_logger)
        if cst and xst:
            st.session_state.capital_session = {"cst": cst, "xst": xst}
            st.rerun()
    st.stop()

tab_preflight, tab_screener = st.tabs([
    "Step 1: Pre-Flight Check (Macro & Curation)",
    "Step 2: Tactical Screener (Rank & Justify)"
])

# === STEP 1: PRE-FLIGHT CHECK (Macro + Curation) ===
with tab_preflight:
    st.header("Step 1: Pre-Flight Check")

    # -- Step 1A: Generate Macro Why --
    with st.container(border=True):
        st.subheader("A. Generate 'Macro Why' (Step 0)")
        macro_news_input = st.text_area(
            "Enter Pre-Market Macro News (The 'Why'):",
            placeholder="e.g., UK CPI hotter than expected, German ZEW weak, Trump tariff threats on XLI...",
            height=100, key="pm_macro_news"
        )
        log1a = AppLogger(st.expander("Step 1A Logs", False), log_key="step1a")

        if st.button("Generate Pre-Market Economy Card", use_container_width=True, key="gen_pm_eco_card"):
            log1a.clear()
            log1a.log("Button clicked: 'Generate Pre-Market Economy Card'")
            with st.spinner("Building Macro Why ..."):
                cst = st.session_state.capital_session.get("cst")
                xst = st.session_state.capital_session.get("xst")
                api_key = load_gemini_keys()[0]  # or random.choice, your pick

                card, error = generate_premarket_economy_card(
                    premarket_macro_news=macro_news_input,
                    logger=log1a,
                    cst=cst,
                    xst=xst,
                    api_key=api_key
                )
                st.session_state.premarket_economy_card = card
                if card:
                    st.session_state.latest_macro_date = card.get("date")
                    log1a.log("Pre-Market Economy Card generated successfully.")
                    st.success("Pre-Market Economy Card generated.")
                else:
                    reason = error or "Unknown error. See logs."
                    log1a.log(f"Failed to generate: {reason}")
                    st.error(f"Failed: {reason}")

        log1a.display_logs()

    if st.session_state.premarket_economy_card:
        st.success("Pre-Market Economy Card is loaded.")
        with st.expander("View Generated Pre-Market Economy Card", False):
            st.json(st.session_state.premarket_economy_card)
    else:
        st.info("Pre-Market Economy Card has not been generated yet.")
    st.markdown("---")

    # -- Step 1B: Proximity Scan & Curation --
    st.subheader("B. Find & Curate 'In-Play' Stocks (Step 1)")

    if not st.session_state.premarket_economy_card:
        st.warning("Step 1B is locked. Complete Step 1A first.")
    else:
        with st.container(border=True):
            col1, col2 = st.columns(2)
            with col1:
                proximity_pct = st.slider(
                    "Proximity Filter (%)", 0.1, 10.0, 2.5, 0.1,
                    help="Find stocks trading within this % distance of a major S/R level."
                )
            log1b = AppLogger(st.expander("Step 1B Logs", False), log_key="step1b")
            with col2:
                if st.button("Scan All Watchlist Tickers", use_container_width=True):
                    log1b.clear()
                    if not st.session_state.latest_macro_date:
                        st.error("Generate the Pre-Market Economy Card first.")
                        st.stop()
                    with st.spinner("Scanning ..."):
                        cst = st.session_state.capital_session["cst"]
                        xst = st.session_state.capital_session["xst"]
                        results = run_proximity_scan(
                            benchmark_date=st.session_state.latest_macro_date,
                            proximity_pct=proximity_pct,
                            logger=log1b,
                            cst=cst,
                            xst=xst
                        )
                        st.session_state.proximity_scan_results = results
                    st.rerun()

            log1b.display_logs()

        if st.session_state.proximity_scan_results:
            st.markdown("##### Curation List")
            st.dataframe(st.session_state.proximity_scan_results, use_container_width=True)
            scan_tickers = [r["Ticker"] for r in st.session_state.proximity_scan_results]
            st.session_state.curated_tickers_for_screener = st.multiselect(
                "Select tickers to send to the 'Head Trader' AI:",
                options=scan_tickers,
                default=scan_tickers
            )
            st.success(f"{len(st.session_state.curated_tickers_for_screener)} tickers ready for Step 2.")
        else:
            st.info("Run the proximity scan to find 'in play' stocks.")

# === STEP 2: TACTICAL SCREENER (Head Trader AI) ===
with tab_screener:
    st.header("Step 2: 'Head Trader' AI Rank & Justify")
    if not st.session_state.premarket_economy_card:
        st.error("Generate the 'Pre-Market Economy Card' (Step 1) first.")
        st.stop()
    curated = st.session_state.curated_tickers_for_screener or []
    if not curated:
        st.error("Run Proximity Scan and select tickers in Step 1.")
        st.stop()
    benchmark_date = st.session_state.latest_macro_date
    st.success(f"Ready to rank {len(curated)} tickers: {', '.join(curated)}")
    st.info(f"Cards are aligned to Macro Benchmark Date: {benchmark_date}")

    executor_focus = st.text_area(
        "Enter Your Personal 'Executor's Focus':",
        placeholder="e.g., Macro is bearish but semis are strong. Looking for long semis or clean shorts.",
        height=100, key="executor_focus"
    )
    log2 = AppLogger(st.expander("Step 2 Logs", False), log_key="step2")
    if st.button("Run 'Head Trader' AI Screener (Step 2)", use_container_width=True, key="run_head_trader"):
        if not executor_focus:
            st.warning("Please provide your 'Executor's Focus'.")
        else:
            log2.clear()
            with st.spinner("Synthesizing tiering/briefing ..."):
                cst = st.session_state.capital_session["cst"]
                xst = st.session_state.capital_session["xst"]
                api_key = load_gemini_keys()[0]
                final_briefing, error = run_head_trader_screener(
                    curated_tickers=curated,
                    benchmark_date=benchmark_date,
                    economy_card=st.session_state.premarket_economy_card,
                    executor_focus=executor_focus,
                    logger=log2,
                    cst=cst,
                    xst=xst,
                    api_key=api_key
                )
                if final_briefing:
                    st.session_state.premarket_screener_output = final_briefing
                    st.success("Head Trader screening complete.")
                else:
                    log2.log(error or "Unknown AI error.")
                    st.error(error or "Unknown AI error.")

    log2.display_logs()

    if st.session_state.premarket_screener_output:
        st.markdown("---")
        st.subheader("Head Trader's Briefing")
        st.markdown(st.session_state.premarket_screener_output, unsafe_allow_html=True)
