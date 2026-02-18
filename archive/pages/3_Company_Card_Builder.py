import streamlit as st
import json
from datetime import datetime, timedelta
from backend.engine.utils import AppLogger, get_turso_credentials
from backend.engine.database import get_db_connection
from backend.engine.gemini import call_gemini_with_rotation
from backend.engine.key_manager import KeyManager

# --- CONFIG ---
st.set_page_config(page_title="Company Card Builder", page_icon="🏭", layout="wide")

# Initialize Helpers
logger = AppLogger(None)
db_url, auth_token = get_turso_credentials()
turso = get_db_connection(db_url, auth_token)

if 'key_manager_instance' not in st.session_state:
    st.session_state.key_manager_instance = KeyManager(db_url, auth_token)
km = st.session_state.key_manager_instance

# --- 1. SESSION STATE SETUP ---
if 'builder_data' not in st.session_state:
    st.session_state.builder_data = {}

st.title("🏭 Company Card Diagnostic Builder")
st.markdown("""
**Purpose:** Use this lab to test the **16-Quadrant Matrix** on individual tickers.
This tool simulates the exact logic that will be used for specific company diagnostics.
""")

# --- 2. INPUT PANEL ---
with st.container():
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. Ticker Context")
        ticker = st.text_input("Ticker Symbol", value="NVDA")
        price = st.number_input("Current Price", value=100.0)
        gap = st.number_input("Gap %", value=2.5)
        
        st.subheader("2. The Trigger (News)")
        news_input = st.text_area("News Catalyst", height=150, value="Breaking: Company announces record earnings beat but lowers forward guidance due to supply chain constraints.")
        
    with col2:
        st.subheader("3. Price Action (30m Blocks)")
        st.info("Simulate the 'Shape' of the session.")
        
        block1 = st.selectbox("Block 1 (Open)", 
            ["Spike Up (Panic Buy)", "Drop (Panic Sell)", "Chop (Indecision)", "Grind Up (Control)", "Grind Down (Control)"])
        
        block2 = st.selectbox("Block 2 (Response)", 
            ["Continuation", "Rejection (V-Shape)", "Absorption (Flat)", "Acceleration"])
        
        block3 = st.selectbox("Block 3 (Current)", 
            ["Holding Highs", "Fading", "New Highs", "New Lows"])

# --- 3. PROMPT GENERATION ---
def generate_company_diagnostic_prompt(ticker, price, gap, news, b1, b2, b3):
    system_prompt = (
        "You are an expert Market Auction Theorist. Your mission is to diagnose the 'What' and 'Why' of this specific ticker's session.\n\n"
        
        "**THE 4-PARTICIPANT MODEL**\n"
        "1. **Committed Buyers (Bargain Hunters):** Price-sensitive, defensive, create U-Shaped bases.\n"
        "2. **Desperate Buyers (Panic-Chasers):** Time-sensitive, offensive, create Vertical-Spikes.\n"
        "3. **Committed Sellers (Value-Exiters):** Price-sensitive, negotiating, create Lower-Highs.\n"
        "4. **Desperate Sellers (Panic-Exiters):** Time-sensitive, binary, create Waterfalls.\n\n"

        "**THE 16-QUADRANT INTERACTION MATRIX (The 'What')**\n"
        "Use this matrix to diagnose the current market condition based on who is present:\n"
        "- **B_Committed vs S_Committed:** 'The Perfect Chop'. Two walls facing off. Precise rotation.\n"
        "- **B_Committed vs S_Desperate:** 'The Slow Bleed & Reversal'. Absorption of panic into a wall.\n"
        "- **B_Committed vs BOTH Sellers:** 'The Bearish Grind'. Wall overwhelmed by the full army.\n"
        "- **B_Committed vs S_Absent:** 'The Slow, Grinding Rally'. Upward drift on low volume.\n"
        "- **B_Desperate vs S_Committed:** 'The Bull Trap'. Violent rejection of fragile aggression.\n"
        "- **B_Desperate vs S_Desperate:** 'Pure Chaos / High Volatility'. Negative edge. Randomness.\n"
        "- **B_Desperate vs BOTH Sellers:** 'The Overwhelmed Rally'. Chasers crushed by the army.\n"
        "- **B_Desperate vs S_Absent:** 'The Fragile Rally'. Unfounded move prone to collapse.\n"
        "- **BOTH Buyers vs S_Committed:** 'The Bullish Grind'. Full army overwhelms the wall.\n"
        "- **BOTH Buyers vs S_Desperate:** 'Short Squeeze / Parabolic Rally'. Running over the panic.\n"
        "- **BOTH Buyers vs BOTH Sellers:** 'The Immovable Object vs. Irresistible Force'. Extreme volume battle.\n"
        "- **BOTH Buyers vs S_Absent:** 'True Bull Trend Day'. Clean, directional, no pullbacks.\n"
        "- **B_Absent vs S_Committed:** 'The Slow Bleed Down'. Downward drift with no opposition.\n"
        "- **B_Absent vs S_Desperate:** 'The Fragile Drop'. Unfounded drop prone to reversal.\n"
        "- **B_Absent vs BOTH Sellers:** 'True Bear Trend Day / Waterfall'. Total surrender.\n"
        "- **B_Absent vs S_Absent:** 'The Dead Market'. Volume vacuum. No auction.\n\n"

        "**THE 'WHAT & WHY' LOGIC**\n"
        "1. **Section 4 (Price Action) is the VERDICT.** Geometry (U-Shape vs. Spike) identifies the participants.\n"
        "2. **Section 3 (News) is the TRIGGER.** News is 'Priced In' by the gap. Analyze the *reaction* to see how the participants processed it.\n"
        "3. **The 'Why':** Explain the interaction between the Trigger and the Verdict. Why did the 'What' occur?\n"
    )
    
    prompt = f"""
    [TICKER DIAGNOSTIC TASK: {ticker}]
    [CONTEXT: Price {price} | Gap {gap}%]
    
    [THE TRIGGER (News/catalyst)]
    {news or "No specific catalyst provided."}
    
    [THE VERDICT (Price Action Geometry)]
    - **Open (Action):** {b1}
    - **Mid (Reaction):** {b2}
    - **Now (Result):** {b3}
    
    [YOUR MISSION]
    Diagnose the specific **Participant Interaction** using the 16-Quadrant Matrix.
    
    [OUTPUT FORMAT]
    Output ONLY a valid JSON object:
    {{
        "diagnostic": {{
            "theWhat": {{
                "interactionCondition": "Name from Matrix",
                "buyerStatus": "Absent / Committed / Desperate / BOTH",
                "sellerStatus": "Absent / Committed / Desperate / BOTH",
                "geometry": "U-Shape / Spike / Waterfall / Grind / ...",
                "description": "Identify who is currently in control and what their intent is."
            }},
            "theWhy": {{
                "triggerAnalysis": "How was the news processed (Acceptance, Rejection, or Ignored)?",
                "negotiationLogic": "Explain the bargaining, intent, and panic shifts that led to the current interaction."
            }}
        }}
    }}
    """
    return prompt, system_prompt

# --- 4. EXECUTION ---
st.divider()
if st.button("🚀 Run Company Diagnostic", type="primary"):
    with st.spinner("Diagnosing Ticker..."):
        prompt, system = generate_company_diagnostic_prompt(ticker, price, gap, news_input, block1, block2, block3)
        
        # Use a reliable model
        model_id = "gemini-2.0-flash-exp" 
        
        resp, err = call_gemini_with_rotation(prompt, system, logger, "gemini-2.0-flash-exp", km)
        
        if err:
            st.error(f"Error: {err}")
        else:
            try:
                # Clean JSON
                clean = resp.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean)
                
                # Render Result
                st.success("Diagnostic Complete")
                
                diag = data.get("diagnostic", {})
                
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader(f"🧩 {diag.get('interactionCondition')}")
                    st.caption(f"Geometry: {diag.get('geometry')}")
                    st.metric("Buyers", diag.get('buyerStatus'))
                    st.metric("Sellers", diag.get('sellerStatus'))
                
                with c2:
                    st.subheader("🧬 The Why")
                    st.write(diag.get('theWhy'))
                
                with st.expander("View Raw JSON"):
                    st.json(data)
                    
            except Exception as e:
                st.error(f"Parsing Error: {e}")
                st.write(resp)
