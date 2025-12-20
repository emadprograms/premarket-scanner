# System Architecture: The Pre-Market Scanner

## 1. Core Philosophy: "Glass Box" AI
This application is designed on the principle of **"Glass Box" AI**. Instead of asking an LLM to "predict the market" (which is hallucination-prone), we construct a **rigid, data-backed "Observation Card"** consisting of mathematical facts (Support/Resistance rejections, Value Migration, Volume profiles) and feed *that* to the AI. The AI's job is purely **synthesis and narrative construction**, not calculation.

## 2. Directory Structure & Key Components

### A. The Front-End (Streamlit Pages)
*   **`app.py`**: The Launchpad. Simple routing script.
*   **`pages/1_📈_Context_Engine.py`**: **THE PRODUCTION COCKPIT**.
    *   This is where the user operates every morning.
    *   **Function**: Loads the "Economy Card" (EOD Context), fetches live Pre-Market data, runs the analysis algorithms, and constructs the Mega-Prompt for Gemini.
*   **`pages/2_🔬_Engine_Lab.py`**: **THE RESEARCH FACILITY**.
    *   An isolated sandbox for testing the market analysis algorithms (`detect_impact_levels`, etc.).
    *   **Data Source**: Can use Real Logic (via `yfinance` or DB) OR "Synthetic Data" (mathematically generated price paths) to stress-test the algo.

### B. The "Brain Stem" (Modules)
Located in `modules/`:
*   **`processing.py`**: **THE HEART OF THE LOGIC**.
    *   **`get_session_bars_from_db()`**: Fetches raw OHLCV data from Turso. **Crucial**: Filters for 04:00 - 09:30 ET (Pre-Market).
    *   **`detect_impact_levels()`**: The "Smart" Algo. Identifies Support/Resistance not by "touches" but by **Rejection Quality** (Magnitude * Log(Duration)).
    *   **`analyze_market_context()`**: The Master Function. Takes raw data, applies the algo, and returns a **JSON Observation Card**. This JSON is what the AI "sees".
*   **`database.py`**: The Data Layer. Handles connections to Turso (libSQL).
*   **`key_manager.py`**: **The Guard Rails**.
    *   Manages a pool of Gemini API keys.
    *   Handles Rate Limiting (Token Bucket), Daily Quotas, and Model Rotation.
    *   **Note**: `gemini-2.5-pro` is currently hardcoded to bypass rate limits for speed.

## 3. The Data Flow Pipeline

1.  **Ingestion**: Market Data (1-min bars) is ingested into Turso DB (via external specific harvester scripts).
2.  **Retrieval**: `Context_Engine` requests data for a specific Ticker & Date.
3.  **Processing** (`modules/processing.py`):
    *   Raw data is sliced to Pre-Market hours.
    *   **Value Migration**: Logic tracks where the "Point of Control" (most traded price) moves every 30 mins.
    *   **Impact Detection**: Logic finds price levels that caused strict reversals.
4.  **JSON Construction**: The logic outputs a structured JSON "Card" (e.g., `{"impact_rejections": [...], "value_migration": [...]}`).
5.  **AI Synthesis**:
    *   This JSON Card + The "Economy Card" (Macro Context) + User News are combined into one massive Prompt.
    *   Gemini (via `modules/gemini.py`) reads this and writes the "Pre-Market Briefing".

## 4. Key Algorithms

### "Impact Score"
How we define a meaningful level:
$$ \text{Score} = \text{Magnitude (Price Drop)} \times \log(1 + \text{Duration (Time until return)}) $$
*   **Magnitude**: How hard did it bounce?
*   **Duration**: How long did the market respect that bounce?
*   *Why Log?* To prevent a 4-hour slow drift from outscoring a violent, instant rejection.

## 5. Deployment Note
*   **API Keys**: Stored in Turso DB (`gemini_api_keys` table), NOT in code.
*   **Environment**: Requires `.streamlit/secrets.toml` with `TURSO_DB_URL` and `TURSO_AUTH_TOKEN`.

## 6. Step 2: Head Trader Synthesis (The Ranking Engine)
The **Head Trader** module (`pages/1_📈_Context_Engine.py` -> Tab 2) is responsible for taking a list of potential setups (from Proximity Scan or Watchlist) and ranking them.

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
