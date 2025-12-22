import streamlit as st

st.set_page_config(
    page_title="Pre-Market Analyst",
    page_icon="🧠",
    layout="wide"
)

st.title("🧠 Pre-Market Analyst Engine")
st.markdown("### *Algorithmic Context & Trade Selection System*")

st.divider()

st.markdown("""
### 🎯 The Mission
This system allows you to act as a **Head Trader** managing a proprietary desk. 
Instead of randomly scanning for "movers", we build a **Thesis-Driven** workflow that aligns
Global Macro Winds with Micro Structure technicals.

We filter the noise to find the **Highest Probability Setups**.
""")

st.divider()

# --- VISUAL ARCHITECTURE ---
col1, col2, col3 = st.columns(3)

with col1:
    st.image("https://img.icons8.com/color/96/forest.png", width=60)
    st.markdown("### Step 1: The Forest")
    st.caption("**Macro Context Engine**")
    st.info("""
    **"Which way is the wind blowing?"**
    
    We synthesize:
    - 📉 **Core Indices Structure** (SPY, QQQ, VIX) to see if markets are migrating Up/Down.
    - 📰 **Overnight News** for sentiment shocks.
    - 🏦 **EOD Context** from the previous session.
    
    **Output:** A confirmed **Market Bias** (Risk-On / Risk-Off).
    """)

with col2:
    st.image("https://img.icons8.com/color/96/tree.png", width=60)
    st.markdown("### Step 2: The Trees")
    st.caption("**Structure & Proximity Scanner**")
    st.warning("""
    **"Who is positioned for a move?"**
    
    We scan your Watchlist for:
    - 🧱 **Structural Confluence**: Are they holding support? 
    - 📍 **Proximity Alerts**: Who is within **0.5%** of a Key Strategic Level defined in your nightly plan?
    
    **Output:** A filtered list of **High-Potential Candidates**.
    """)

with col3:
    st.image("https://img.icons8.com/color/96/apple.png", width=60)
    st.markdown("### Step 3: The Fruit")
    st.caption("**Head Trader AI Ranking**")
    st.success("""
    **"Which trade is the ripest?"**
    
    The AI acts as your **Senior Risk Manager**:
    - ⚖️ **The Courtroom**: Compares the *Strategic Plan* (Thesis) vs. *Tactical Reality* (Tape).
    - 🏅 **Ranking**: Sorts setups by Macro Alignment & Narrative Consistency.
    
    **Output:** A Final **Ranked Trade Plan**.
    """)

st.divider()

st.markdown("### 🚀 How to Run the System")

st.markdown("""
1. Navigate to **`📈 Context Engine`** in the sidebar.
2. **Step 1**: Click **`Generate Macro Context`** to set the session bias.
3. **Step 2**: Check the **`Structural Scanner`** table. Use **`Proximity Logic`** to find tickers near key levels.
4. **Step 3**: Select your top candidates and hit **`🧠 Run Head Trader`** for the final verdict.
""")

st.info("💡 **Pro Tip**: Use the `Simulation Mode` in the sidebar to test this workflow on historical dates!")