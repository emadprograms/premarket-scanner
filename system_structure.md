# System Architecture: The Pre-Market Scanner

## 1. Core Philosophy: "Glass Box" AI
This application is designed on the principle of **"Glass Box" AI**. Instead of asking an LLM to "predict the market" (which is hallucination-prone), we construct a **rigid, data-backed "Observation Card"** consisting of mathematical facts (Support/Resistance rejections, Value Migration, Volume profiles) and feed *that* to the AI. The AI's job is purely **synthesis and narrative construction**, not calculation.

## 2. Directory Structure & Key Components

### A. The Backend (FastAPI)
Located in `backend/`:
*   **`main.py`**: The entry point for the FastAPI server. Orchestrates routers and WebSocket connections.
*   **`routers/`**: API endpoints for different features.
    *   `macro.py`: Handles Step 0 related logic (Economy Card).
    *   `scanner.py`: Handles Step 1 related logic (Data fetching and analysis).
    *   `ranking.py`: Handles Step 3 related logic (Ranking setups).
    *   `system.py`: System health checks and context management.
*   **`services/`**: Helper services.
    *   `context.py`: Singleton management for Database and keys.
    *   `logger.py`: Centralized logging service.
    *   `socket_manager.py`: Real-time WebSocket communication.
*   **`engine/`**: **THE CORE BRAIN**. 
    *   **`processing.py`**: The heart of the technical analysis. Detects impact levels, routes data (Capital -> Yahoo -> DB), and calculates staleness.
    *   **`analysis/macro_engine.py`**: Implements the **60/40 Synthesis** and distillation of historical logs.
    *   **`analysis/detail_engine.py`**: Generates tactical "Company Battle Cards".
    *   **`capital_api.py`**: Handles Capital.com session management and data fetching.
    *   **`database.py`**: Manages Turso interactions and local caching.
    *   **`key_manager.py`**: V8 model rotation and rate limiting.
    *   **`sync_engine.py`**: Logic for synchronizing state or data.
    *   **`sentiment_engine.py`**: Placeholder for future sentiment analysis features.

### B. The Front-End (Next.js)
Located in `frontend/`:
*   **`src/app/`**: The Next.js App Router structure.
    *   `page.tsx`: Single-page entry point.
    *   `layout.tsx`: Root layout definition.
*   **`src/components/layout/`**:
    *   **`MissionControl.tsx`**: The main cockpit ("Commander"). Orchestrates the Economy Card, Scanner Grid, and Ranking view in a single unified interface.
    *   `Shell.tsx`: Application shell/wrapper.
*   **`src/components/ui/`**: Reusable UI atoms and molecules.

### C. Legacy & Archive
*   **`archive/`**: Contains previous implementations and deprecated files.

## 3. The Data Flow Pipeline

1.  **Ingestion**: 
    *   Primary: **Capital.com API** (Real-time).
    *   Secondary: **Yahoo Finance** (Fallback if Capital fails/missing data).
    *   Tertiary: **Turso DB** (Historical/Simulation mode).
2.  **API Request**: Frontend (`MissionControl`) sends requests to FastAPI routers (`/api/macro`, `/api/scanner/scan`).
3.  **Context Construction** (`macro_engine.py`):
    *   Previous Economy Card (60% weight).
    *   News & Sector ETFs (40% weight).
    *   Summarized Action Log (Macro Arc).
4.  **Stock Deep Dive** (`processing.py` + `detail_engine.py`):
    *   Price Action (Value Migration + Impact Levels).
    *   Staleness Checks (Gap Guard).
5.  **Final Ranking** (`ranking.py`):
    *   Synthesizes Economy Card + Battle Cards into prioritized trade plans.
6.  **Real-Time Feedback**: Progress logs pushed to the frontend via WebSockets (`/ws/logs`).

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

## 5. Deployment & Configuration
*   **Backend**: FastAPI running via Uvicorn (Port 8000).
*   **Frontend**: Next.js running in dev/production mode (Port 3000).
*   **Secrets**: Managed via **Infisical**. Requires `TURSO_DB_URL`, `TURSO_AUTH_TOKEN`, and Gemini API Keys.

## 6. The Ranking Engine (Head Trader Synthesis)
The **Ranking Engine** (Step 3) takes potential setups and ranks them using a **3-Layer Validation Model**:
1.  **Macro Alignment (The Wind)**: Does the trade align with the day's broad market bias?
2.  **Strategic Confluence (The Map)**: Is price interacting with a level we *planned* for in the EOD Card?
3.  **Tactical Reality (The Terrain)**: Is the price *actually* respecting the level right now (Migration Blocks, Rejections)?

## 7. Troubleshooting History & Robustness Logic 

### A. Capital.com API Concurrency
*   **Solution**: Sequential data fetching with 1s delays to avoid 429 errors. Parallel CPU processing for analysis once data is in memory.

### B. The "Weekend Wall"
*   **Solution**: Fallback to higher resolutions (15m, 1h) or DB-only mode when 1m data is unavailable during market close.

### C. Data Fallback Strategy (The "Gap Guard")
*   **Primary**: Capital.com.
*   **Fallback**: Yahoo Finance (for missing tickers or API failures).
*   **Safety**: Stale data (>60m old in pre-market) is discarded to prevent stale analysis.
*   **Ultimate**: If all live sources fail, system falls back to Turso DB "Hot Desks" (EOD plans).

## 8. The Anchor & Delta Framework (Narrative Momentum)
*   **The Anchor (EOD Card)**: Defines the "Prior Belief".
*   **The Delta (Live/Pre-Market)**: Captures evidence of break or validation from today's action.
*   **Integrity Test**: Binary check (HOLDING vs. BREAKING) to determine if pre-built plans are still valid.

## 9. The Step 1 Unified Workflow
1.  **Check**: Is Live Data Fresh? (Staleness < 60m).
2.  **Fetch**: Capital -> Yahoo -> DB.
3.  **Analyze**: Generate Observation Card (Migrations, Impact Levels).
4.  **Rank**: Apply Head Trader logic.

## 10. The Psychological Framework (The "Senior Analyst" Mindset)
*   **Institutional Voice**: AI sounds like a professional desk lead, not an academic.
*   **Hierarchy of Truth**: Price Action > Volume Support > 3-Act Arc.
*   **Brutal Honesty**: AI must explicitly state if data is missing rather than hallucinating.
