# System Architecture: The Pre-Market Scanner

## 1. Core Philosophy: "Glass Box" AI
This application is designed on the principle of **"Glass Box" AI**. Instead of asking an LLM to "predict the market" (which is hallucination-prone), we construct a **rigid, data-backed "Observation Card"** consisting of mathematical facts (Support/Resistance rejections, Value Migration, Volume profiles) and feed *that* to the AI. The AI's job is purely **synthesis and narrative construction**, not calculation.

## 2. Directory Structure & Key Components

### A. Root Directory
*   **`app.py`**: **THE PRODUCTION COCKPIT**.
    *   This is where the user operates every morning.
    *   **Function**: Loads the "Economy Card" (EOD Context), fetches live data, runs analysis, and triggers the Gemini Masterclass synthesis.
*   **`.venv/`**: Python virtual environment (Python 3.12+). **(Not tracked in Git)**

### B. The Front-End (Ancillary Pages)
*   **`pages/1_Capital_Epic_Diagnostic.py`**: **DIAGNOSTIC TERMINAL**.
    *   Used for verifying API connections and mapping.
*   **`pages/2_🔬_Engine_Lab.py`**: **THE RESEARCH FACILITY**.
    *   An isolated sandbox for testing the market analysis algorithms (`detect_impact_levels`, etc.).
    *   **Data Source**: Can use Real Logic (via `yfinance` or DB) OR "Synthetic Data" (mathematically generated price paths) to stress-test the algo.

### C. The "Brain Stem" (Modules)
Located in `modules/`:
*   **`processing.py`**: **THE HEART OF THE LOGIC**.
    *   **`get_session_bars_routed()`**: Routes data fetching based on Live/Simulation mode.
    *   **`detect_impact_levels()`**: Identifies Support/Resistance rejections using Magnitude * Log(Duration).
*   **`analysis/macro_engine.py`**: **THE MACRO STRATEGIST**.
    *   Implements the **"60/40 Synthesis"** logic (60% Trend bias from Previous Card, 40% Today's Data).
    *   Uses **"summarize_rolling_log"** to distill historical actions into a Macro Arc (Origins, Transformation, Immediate Regime).
    *   Follows the **3-Act Structure** for session analysis.
*   **`analysis/detail_engine.py`**: **THE TACTICAL ANALYST**.
    *   Generates deep-dive "Battle Cards" for individual stocks.
    *   Aligns local price action with Macro Context.
*   **`database.py`**: Handles connections to Turso (libSQL) and the Local Cache.
*   **`key_manager.py`**: **The Guard Rails**.
    *   V8 manages isolated model buckets (RPM/TPM/RPD).
    *   Maps display names to valid Gemini model IDs (including Gemini 2.0).
*   **`gemini.py`**: Rotation logic for API calls.

## 3. The Data Flow Pipeline

1.  **Ingestion**: Market Data (1-min bars) into Turso.
2.  **Context Construction** (`macro_engine.py`):
    *   Previous Economy Card (60% weight).
    *   News & Sector ETFs (40% weight).
    *   Summarized Action Log (Macro Arc).
    *   Result: A comprehensive **Economy Card**.
3.  **Stock Deep Dive** (`detail_engine.py`):
    *   Price Action (Value Migration + Impact Levels).
    *   Macro Alignment.
    *   Result: **Company Battle Cards**.
4.  **Final Ranking** (`app.py` Step 3):
    *   Synthesizes Economy Card + Battle Cards into prioritized trade plans.

## 4. Key Logic & Constraints

### 60/40 Synthesis Rule
*   **60% Weight**: Governing Trend (Previous Bias). Trends are "heavy".
*   **40% Weight**: Today's Data (News + ETF Evidence).
*   **Reversal Condition**: Requires High Conviction evidence to flip the trend.

### 3-Act Structure
Analysis is broken into:
*   **Act I (Open/Pre-Market)**: Market Intent.
*   **Act II (RTH)**: Acceptance or Rejection of intent.
*   **Act III (Close)**: Verified Outcome.

### Price Scaling Awareness
The system detects scale differences between ETFs (e.g., QQQ) and Index CFDs (e.g., NAS100) and provides "Scaling Notes" to the AI to prevent level hallucinations.

## 5. Deployment & Configuration
*   **Gemini Models**: Supports Gemini 2.0 Flash/Pro/Thinking.
*   **Environment**: Requires `TURSO_DB_URL`, `TURSO_AUTH_TOKEN`, and Infisical for secret management.

## 6. Step 2: Head Trader Synthesis (The Ranking Engine)
The **Head Trader** module (`app.py` -> Tab 2) is responsible for taking a list of potential setups (from Proximity Scan or Watchlist) and ranking them.

### Core Logic: The Narrative Synthesizer
Unlike traditional scanners that rank by "% Change", this system ranks by **Narrative Alignment**. It uses a **3-Layer Validation Model**:

1.  **Macro Alignment (The Wind)**
    *   **Input**: The "Economy Card" generated in Step 0.
    *   **Logic**: Does this trade align with the day's broad market bias (e.g., Risk-On, Sector Rotation)?
    *   *Example*: If the Market is "Bearish Tech", a Long AAPL setup is penalized.

2.  **Strategic Confluence (The Map)**
    *   **Input**: The "Strategic Plan" (fetched from `company_cards` table in DB).
    *   **Components**:
        *   **Narrative Note**: The multi-day story for this ticker.
        *   **Screener Briefing**: Specific prep instructions for the AI.
        *   **Planned Levels**: Major Support/Resistance defined the night before.
    *   **Logic**: Is price interacting with a level we *planned* for? Is the story consistent?

3.  **Tactical Reality (The Terrain)**
    *   **Input**: Real-time Pre-Market Price Action (from `glassbox_raw_cards`).
    *   **Logic**: Is the price *actually* respecting the level right now (e.g., Migration Blocks, Impact Rejections)?

### Result
The AI outputs a **Ranked List** (Tier 1: "Top Conviction", Tier 2: "Interesting", Tier 3: "Ignore") with a specific reasoning: *"Tier 1: MSFT is actionable because it is holding Planned Support (Layer 2) which aligns with today's Tech Rotation (Layer 1)."*

## 7. Troubleshooting History & Robustness Logic 

This section serves as a historical database for future agents/developers regarding challenges encountered with the Capital.com API and the solutions implemented.

### A. Capital.com API Concurrency & Rate Limits
- **Problem**: Simultaneous requests (parallelization) to Capital.com caused "Dynamic Failures" (intermittent 400/429/connection drops) where the success rate fluctuated between 20% and 80%.
- **Finding**: Capital.com strictly enforces a **1 request per second** rate limit and prefers/requires **Sequential Session Management**.
- **Solution**: 
    - Implemented **Phase-Separated Scanning**: Data is fetched **Sequentially** with a forced 1-second `time.sleep()` delay.
    - Once data is in memory, the **Technical Analysis** (CPU processing) is run in **Parallel** to maintain overall app speed.

### B. The "Weekend Wall" (Lookback Limits)
- **Problem**: 1-minute data fetching for indices/stocks returned "No data" on weekends, leading to false-negative connection tests.
- **Finding**: Capital.com's Free Tier has a hard **16-hour lookback limit** for 1-minute granularity. If markets have been closed for longer than 16 hours, the buffer is empty.
- **Solution**: 
    - Created a **Multi-Resolution Diagnostic Terminal**.
    - For weekend testing, switching resolution to **MINUTE_15, HOUR, or DAY** allows the system to pull historical Friday data and verify Epic mapping/Auth status.

### C. Authentication & DB Fallback
- **Problem**: API authentication failures (expired CST/XST tokens) would block the entire application start.
- **Solution**: 
    - Enhanced error guidance to suggest the **"DB Fallback"** toggle in the Mission Config. 
    - This allows the app to bypass live API failures and utilize Turso historical data to maintain operational "Hot Desks" for simulation and planning.

## 8. The Anchor & Delta Framework (Narrative Momentum)

The system treats the trading session as a transition from a **Prior Narrative** to **New Evidence**.

### A. The Anchor (EOD Card)
*   **Source**: The latest "Strategic Plan" or "Economy Card" generated at the previous close.
*   **Role**: Defines the "Prior Belief" and established zones. The AI assumes this narrative holds the "Path of Least Resistance."

### B. The Delta (Live/Pre-Market Card)
*   **Source**: Analysis of the last **2.9 days** of history (to capture multi-day structure).
*   **Filtering**: Technical events (Value Migrations, Rejections) are filtered to only show developments that occurred **after the current session's Pre-Market Open**.
*   **Role**: Provides the "Evidence of Break." It reports only the new friction points that the AI must weigh against the Anchor.

### C. Binary Narrative Integrity Test
The AI performs a binary check (HOLDING vs. BREAKING) on the Anchor narrative:
*   **HOLDING**: Today's Delta aligns with or respects the Anchor's zones. Action: Pre-built plans for individual stocks remain valid.
*   **BREAKING**: Today's Delta (price action or news) fundamentally voids the Anchor. Action: Pre-built stock plans are now "Ambiguous" or "Failed." The system prioritizes tight tactical tape-reading over the stale strategy.
## 9. The Step 1 Unified Workflow & Gap Guard

To optimize both user workflow and API credit usage, Step 1 uses a **Fail-Safe Unified Workflow**.

### A. Unified Execution
Data fetching (historical + live) and AI synthesis are merged into a single sequential operation. However, the system is designed to **pause** if the data is not optimal.

### B. The Gap Guard (Fail-Safe)
Before making an expensive LLM call, the system performs a multi-point check:
1.  **Critical Gaps**: If any tickers failed to fetch or analysis failed, the process stops.
2.  **Staleness Alert**: If the fetched data is older than 1 hour, the process stops.

### C. Explicit User Consent
When a gap or stale data is detected:
*   The system updates the status to "Warning/Error" and performs a `st.rerun()`.
*   An **Explicit Confirmation UI** appears at the top of the results.
*   The user must click **"🚀 Proceed Anyway (Use Credits)"** to trigger the AI, or **"🔄 Retry"** to fix the data. This prevents wasted credits on broken narratives.

### D. UI Prioritization
In the results tab, **Data Verification** (alerts, tables, charts) is placed at the absolute top. This ensures that any technical issues are revealed to the trader before they ever read the AI narrative.

## 10. The Psychological Framework (The "Senior Analyst" Mindset)

The system is not just a calculator; it is a **Decision Support System** built around the mindset of a **Senior Trading Desk Lead**.

### A. The AI Persona: "The Institutional Voice"
The AI synthesis explicitly avoids academic or amateur language. It is instructed to sound like a professional trader (e.g., Bloomberg/Institutional Desk):
*   **Trigger vs. Verdict**: News is the **Trigger** (Intent), but Price Action is the **Verdict** (Reality).
*   **Professional Terminology**: Instead of retail-focused terms, it describes participant behavior using "Institutional Support," "Aggressive Selling," "Price Discovery," and "Risk-off Rotation."

### B. The 4-Participant Model (Behavioral Sentiment)
The AI interprets price action through the lens of **Absence and Exhaustion**:
1.  **Committed Buyers/Sellers**: Patient participants who accumulate/distribute at key levels. They define **Stable Markets**.
2.  **Desperate Buyers/Sellers**: FOMO or Panic-driven participants who act at any price. They cause **Unstable Markets** (Capitulations or Blow-offs).

### C. The Hierarchy of Truth
1.  **Truth #1: Price Action**: If news is bad but price rallies, the AI reports a "Bullish Surprise" (High Conviction).
2.  **Truth #2: Volume Support**: High-volume rejections prove the presence of Committed Participants.
3.  **Truth #3: The 3-Act Arc**: Every session is analyzed as a multi-act play:
    *   **Act I (Intent)**: What did the Pre-Market try to do?
    *   **Act II (Conflict)**: Did the RTH migration validate or invalidate that intent?
    *   **Act III (Resolution)**: Did the close confirm its control or was it a failed reversal?

### D. Data Integrity & Anti-Hallucination
A core part of the "Psychological Trust" in the system is its **Brutal Honesty**:
*   **Acknowledge Missing Data**: The AI is strictly forbidden from guessing. If a ticker like "QQQ" or "VIX" is missing from the scan, it must explicitly state **"Data not provided"**.
*   **Gap Guard**: This ensures the user is never reading a "hallucinated narrative" based on incomplete data without their explicit consent.
