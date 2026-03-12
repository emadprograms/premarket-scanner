# Pre-Market Scanner: The Proximity Engine Constitution

## 1. Core Identity: The Mathematical Ranking Tool
- **Primary Goal**: To rank stocks in real-time based *solely* on the proximity of their current price to established "Plan A" or "Plan B" levels.
- **No AI**: All AI synthesis, narrative generation, and "Institutional Voice" components are removed. The program is a pure measurement and sorting utility.
- **Trader-Centric**: The program provides the proximity data; the human trader makes all decisions regarding tradability, level breaks, and execution.

## 2. Operational Guardrails (CRITICAL)
- **Separation of Concerns**: Pre-Market Scanner and Archive Room are to be treated as **completely separate applications**. When working on either of them, the other one must remain entirely unaffected and untouched. Modifications to the Archive Room must not break the Pre-Market Scanner, and modifications to the Pre-Market Scanner must not break the Archive Room. They are separate programs.
- **Cleanup**: Any references found to the old **Analyst Workbench** should be immediately removed. If there are any references to the Analyst Workbench that might be found in the Pre-Market Scanner or Archive Room, the user should be informed.

## 3. The Ranking Logic (The Proximity Score)
- **Metric**: Distance is calculated as the gap between the current price and the nearest plan level (Plan A or Plan B).
- **Normalisation**: Proximity must be normalized (using ATR or similar volatility-adjusted metrics) to ensure stocks of different price ranges (e.g., $100 vs $500) are ranked fairly relative to their typical movement.
- **Hierarchy**:
    - **Rank 1**: Closest to a Plan level.
    - **Tie-Breaker**: Plan A levels take priority over Plan B levels if distances are equal.
- **Agnostic to Breaks**: The program does not care if a level is "broken" or "held." It only reports the distance to the level coordinate.

## 4. Technical Standards & Secrets (Infisical)
- **SDK**: Always use the **`infisical-sdk`** package. **DO NOT** use the deprecated `infisical-python`.
- **Manager Pattern**: Logic is encapsulated in `backend/engine/infisical_manager.py`. It handles the client initialization and authentication state.
- **WebSocket Aggregator**: The backend must maintain a persistent WebSocket connection to Capital.com for all watchlist tickers. REST polling for price data is strictly deprecated.
- **Real-Time UI**: The frontend list must re-sort dynamically as WebSocket price updates trigger new proximity calculations.

## 5. Database Schema & Table Names (CRITICAL)
All tables live in the remote Turso database. The `aw_` prefix stands for "Analyst Workbench" (legacy naming).

| Table | Purpose | Key Columns |
|---|---|---|
| `aw_ticker_notes` | **Watchlist source** — contains all active tickers | `ticker`, `historical_level_notes` |
| `aw_economy_cards` | Economy/macro analysis cards (one per trading day) | `date`, `economy_card_json` |
| `aw_company_cards` | Per-ticker company analysis cards (sole source for screener) | `ticker`, `date`, `company_card_json` |
| `premarket_snapshots` | Full session snapshots | `run_timestamp`, various JSON blobs |
| `daily_inputs` | Daily news text inputs | `target_date`, `news_text` |
| `symbol_map` | Ticker-to-epic mapping for Capital.com | `ticker`, `epic` |

> **IMPORTANT**: The old `Stocks` table is **deprecated and removed**. The watchlist is now sourced from `aw_ticker_notes`. The old `economy_cards` and `company_cards` tables are renamed to `aw_economy_cards` and `aw_company_cards`.

## 6. Backend Architecture & Known Patterns

### libsql_client Threading (CRITICAL)
The `libsql_client` v0.3.1 sync wrapper (`create_client_sync`) runs its own internal event loop on a background thread. When called from FastAPI's async endpoints:
- **Simple queries** (e.g., `SELECT 1`) work fine from async context.
- **Parameterized queries or queries on missing tables** can crash with `KeyError: 'result'` due to HTTP transport protocol parsing errors.
- **Fix**: Wrap all DB calls in `asyncio.to_thread()` when calling from async FastAPI endpoints, or use the `_safe_execute()` pattern in `archive.py`.

### Error Response Pattern
The backend uses `GenericResponse(status="error", message="...")` which returns HTTP 200 with a JSON body containing `status: "error"`. The frontend **must** check `response.status` (not just HTTP status code) to detect logical errors.

### Capital.com WebSocket
- Auth requires `capital_com_x_cap_api_key`, `capital_com_identifier`, `capital_com_password` from Infisical.
- WS startup is **non-fatal** in the scanner — if auth fails, the scan continues using historical data from the database.
- The WS service retries auth every 10 seconds in the background.
- **Epic→Ticker Mapping**: Capital.com uses EPICs (e.g. `US500` for SPY). The `_epic_to_ticker` reverse map in `capital_socket.py` translates these back to user tickers before broadcasting to the frontend. Without this, price updates will silently fail to match.
- **Frontend Connection**: The header bar has a "Connect/Disconnect to Capital.com" button. Connection is NOT automatic — user must explicitly click Connect to start live streaming.

### Card Extractor (`backend/engine/card_extractor.py`)
- **Dedicated module** for extracting plan data from company card JSON.
- Handles **both formats**: JSON dict (`{"Plan_A_Level": "255.84"}`) and raw string (`Plan_A_Level: $255.84`).
- Extracts: `plan_a_level`, `plan_b_level`, `plan_a_text`, `plan_b_text`, `plan_a_nature`, `plan_b_nature`, `setup_bias`.
- **Plan nature** (SUPPORT/RESISTANCE) is classified from the plan description text using keyword scoring (e.g. "Long Support Defense" → SUPPORT). **NOT** from S_Levels/R_Levels — those are for reference only.
- `scanner.py` uses `extract_screener_briefing()` exclusively — no inline regex extraction.

### Economy Card Persistence
Economy cards are saved in two places:
1. **Local JSON cache**: `data/economy_card_cache.json` (fast read for status checks)
2. **Turso DB**: `aw_economy_cards` table (persistent, used by Archive Room)

Both are written by `macro.py` when a macro analysis completes.

## 7. Frontend Architecture

### Key Files
| File | Role |
|---|---|
| `frontend/src/app/page.tsx` | Main scanner view — auto-loads baseline data, reactive ranking, card grid |
| `frontend/src/lib/context.tsx` | `MissionProvider` — global settings, system status, `capitalStreaming` state |
| `frontend/src/lib/api.ts` | Axios API client (base URL auto-detection) |
| `frontend/src/lib/socket.ts` | WebSocket client — price updates + log streaming, with `offPriceUpdate` cleanup |
| `frontend/src/components/layout/Shell.tsx` | App shell with Connect/Disconnect Capital.com button in header |
| `frontend/src/components/layout/CardEditorView.tsx` | Archive Room — economy/company card viewer |
| `frontend/src/components/layout/EconomyCardView.tsx` | Economy card renderer |
| `frontend/src/components/layout/CompanyCardView.tsx` | Full company card renderer (used via "Show Full Card" toggle) |
| `frontend/src/components/layout/ScreenerBriefingView.tsx` | Screener briefing popup — shows story, catalyst, pattern, Plan A/B with S/R coloring |
| `backend/engine/card_extractor.py` | Robust extraction of plan levels & nature from card JSON |
| `backend/services/capital_socket.py` | Capital.com WebSocket singleton — price streaming with epic→ticker reverse map |

### Data Shape Contract (Archive)
The archive API returns cards with these exact field names — the frontend components depend on them:
- Economy: `{ date, economy_card_json: {...} }`
- Company: `{ ticker, date, company_card_json: {...} }`

## 8. Evolution & Decision Log (Troubleshooting & Core Reasoning)
- **Decision: Modal Click-Outside-to-Close**: Added an `onClick` handler to the `Modal` backdrop that compares `e.target === e.currentTarget` to allow closing modals by tapping anywhere outside the card area, improving UX for chart and briefing views.
- **Decision: Yahoo Finance Chart Integration (Weekend Fallback)**: Implemented a dual-source data fetching model. Users can toggle between **Capital.com** (intraday) and **Yahoo Finance** (fallback/weekend) in `ChartPlanView.tsx`. A new backend endpoint `/api/scanner/bars/yahoo/{ticker}` normalizes Yahoo data for the chart.
- **Decision: Chart Session Backgrounds**: Added dynamic amber (Pre-market) and blue (Post-market) background tints to charts. These recalculate when switching data sources to account for timezone alignment differences.
- **Decision: Capital.com WebSocket Event Loop Fix**: Wrapped synchronous `requests.post()` calls in `create_capital_session_v2` with `asyncio.to_thread()` to prevent blocking the FastAPI event loop.
- **Decision: Token Cache Expiry**: Added an 8-minute TTL (`480s`) to Capital.com session tokens to refresh them before the 10-minute API limit, preventing "stale token" reconnection loops.
- **Decision: Application-Level Pings**: Replaced WebSocket protocol pings with Capital.com's expected JSON-level ping (containing `cst`/`securityToken`) every 30s to maintain connection integrity.
- **Decision: Exponential Backoff**: Implemented 5s → 10s → 20s → 60s backoff for WebSocket reconnection failures to avoid spamming the API during outages.
- **Decision: Switch to Cloudflare Tunnel**: Replaced ngrok with Cloudflare Tunnel (`cloudflared`) for unlimited bandwidth and improved background stability. Updated setup scripts and GitHub Actions.
- **Decision: Discord Bot Integration**: Added the Vercel frontend link to the `!turnon` command output so traders can jump straight to the live scanner.
- **Decision: CORS & Vercel Hardening**: Set `allow_credentials=False` and `expose_headers=["*"]` to ensure compatibility with Cloudflare's tunnel and Vercel's cross-origin requirements.
- **Decision: Frontend API URL Resolution**: Fixed `getBaseUrl()` to handle Vercel deployments correctly, preventing the appending of `:8000` to production hostnames.
- **Decision: Removal of AI**: We removed all LLM-based narrative generation because it introduced latency and hallucinations. The "Senior Desk Lead" identity now manifests as mathematical precision in ranking, not verbal analysis.
- **Decision: Proximity over Percentage**: We moved to ATR-normalized proximity because a $1 move on a $100 stock is not the same as a $1 move on a $500 stock. This ensures the "Tradability" ranking is volatility-aware.
- **Decision: Backend Host Binding**: Changed backend binding from `127.0.0.1` to `0.0.0.0` to resolve connectivity issues where the frontend couldn't reach the backend due to IPv4/IPv6 resolution ambiguity.
- **Decision: Robust API Base URL**: Updated `frontend/src/lib/api.ts` to dynamically detect the hostname. Crucially, it now forces `127.0.0.1` when `localhost` is detected to bypass macOS IPv6 resolution issues.
- **Decision: Connection Error States**: Implemented a dedicated "Connection Failure" UI in the scanner to distinguish between "Backend Offline" (API unreachable) and "Empty Data" (API active but no tickers found). This prevents confusing "Loading" loops when the server is down.
- **Decision: CORS Simplification**: Removed `allow_credentials=True` from `backend/main.py` CORS middleware to prevent preflight blocks.
- **Decision: Infisical SDK Migration (Problem & Resolution)**:
    - *Problem*: Initial attempts to use `infisical-sdk` failed because the correct PyPI package name is actually **`infisicalsdk`**.
    - *Reasoning*: The deprecated `infisical-python` used older method signatures. The new `infisicalsdk` (v1.0.16+) uses `get_secret_by_name` and `list_secrets` with mandatory keyword arguments and specific return objects (like `BaseSecret.secretValue`).
- **Decision: Singleton InfisicalManager (Problem & Resolution)**:
    - *Problem*: Backend hung on startup due to race conditions when multiple threads (Main API + Gemini Key Sync Thread) attempted to initialize the Infisical Client simultaneously.
    - *Reasoning*: Implementing a **Singleton pattern** ensures only one client/authentication state exists, preventing port-binding delays and credential-fetching deadlocks.
- **Decision: Capital.com WebSocket Payload Format**: Discovered that Capital.com's WebSocket API requires the `cst` and `securityToken` to be passed at the root level of the `marketData.subscribe` payload, rather than through a separate `control.session` handshake. The incoming message destination for live prices is also labeled `"quote"`, not `"market.update"`.
- **Decision: Separation of Scanner & Archive**: To prevent "bricking" the system, we decoupled the live ranking environment (Scanner) from the historical management environment (Archive). They operate on different API routes and logic flows.
- **Decision: Table Rename to `aw_` Prefix**: All card tables were renamed from `economy_cards`/`company_cards` to `aw_economy_cards`/`aw_company_cards`. The watchlist source moved from the deprecated `Stocks` table to `aw_ticker_notes`. All backend routers, database functions, and the sync engine were updated.
- **Decision: Non-Fatal Capital.com WS**: The scanner's Capital.com WebSocket startup is wrapped in try/except so the scan completes using historical data when auth fails, rather than crashing the entire endpoint.
- **Decision: Null-Safe Scanner Output**: The scanner output formatter handles `None` values for `nearest_level_value` (when no Plan A/B levels exist) to prevent `TypeError` crashes.
- **Decision: ATR Indentation Fix**: The `calculate_atr()` function in `processing.py` had a critical indentation bug where the entire ATR calculation was nested inside an early-return `if` block, making it unreachable dead code. Fixed by correcting indentation.
- **Decision: Retired `deep_dive_cards`**: The scanner now exclusively uses `aw_company_cards` for card data. Fetches the **latest card per ticker** with no date cap (always the most recent card). The `deep_dive_cards` table is no longer queried.
- **Decision: Card Date Display**: Each card shows a date indicator (e.g. `Card: 2026-02-17`) so the user knows how fresh the screener briefing data is.
- **Decision: No-Price Tickers Kept**: Tickers without a live price are no longer dropped from the response. They appear at the end of the list with `--` for price/proximity and no rank badge, using a neutral gray card border.
- **Decision: Dual Nature Labels**: Cards show **two** labels: (1) `PLAN: SUPPORT/RESISTANCE` — what the plan text classifies the level as, (2) `↑ ABOVE / ↓ BELOW` — whether the live price is currently above or below the nearest level.
- **Decision: Epic→Ticker Reverse Map Fix**: The `capital_socket.py` was broadcasting `"ticker": epic` (e.g. `"US500"`) but the frontend mapped prices by user ticker (`"SPY"`). Fixed by storing an `_epic_to_ticker` reverse map and broadcasting the user ticker.
- **Decision: Screener Briefing as Secondary View**: The screener briefing (story, justification, catalyst, Plan A/B with S/R coloring) is now accessible via a prominent "Read Screener Briefing" button below the chart. The chart with plan levels is the primary view when clicking a card.
- **Decision: Plan Nature from Plan Text Only**: SUPPORT/RESISTANCE classification comes exclusively from the plan description text (e.g. "Long Support Defense" → SUPPORT). S_Levels and R_Levels are **NOT** used for classification — they are reference data only.
- **Decision: Frontend Connect/Disconnect Control**: The header bar has an explicit Connect/Disconnect button for Capital.com streaming. Connection is user-initiated, not automatic. The old MissionControl component and Live Ranking Feed were removed.
- **Decision: Violet Purple Theme**: Changed `--primary` from green (`#00cc96`) to violet (`#8b5cf6`). Green was misleading in a trading context (confused with bullish signals). Green is now reserved exclusively for SUPPORT labels, status dots (connected/healthy), and MARKET OPEN badge. Red stays for RESISTANCE and error states.
- **Decision: Proximity Shows '--' Without Streaming**: Both proximity and live price display `--` when Capital.com is not connected, since proximity is meaningless without a live price feed.
- **Decision: Robust Retry & Auto-Recovery**: The initial scan retries 3 times with 3s backoff before showing offline. Status polling is adaptive (10s when offline for fast recovery, 30s when connected). When the status poll detects the backend is back, it auto-triggers a scan retry — no manual reload needed. The "Retry Connection" button calls `loadBaseline()` directly instead of a full page reload.
- **Decision: Silent Error Handling**: `console.error` calls for network failures were replaced with `console.warn` or removed entirely to prevent Next.js dev overlay from showing ugly stack traces. The "Connection Offline" UI and status bar handle error display visually.
- **Decision: Axios Timeouts**: Global timeout is 30s (covers status, config). The scan endpoint gets 60s since it processes 20+ tickers with ATR + DB queries.
- **Decision: Chart-First Modal**: Clicking a card shows a lightweight-charts candlestick chart with only the **nearest plan level** plotted as a **dashed** price line (violet for SUPPORT, red for RESISTANCE). Only the actionable trade is shown — secondary plan and "NOW" live price lines are omitted to reduce clutter. Plan level info cards below show both plans. The flow is: Chart → Briefing → Full Card.
- **Decision: Yahoo for ATR, Capital for Chart**: The initial scan uses **Yahoo Finance** for ATR calculation (fast, ~2s for all tickers) instead of Capital.com (slow, 20+ sequential API calls). Chart plotting uses **Capital.com** via `/api/scanner/bars/{ticker}` (accurate pre-market data, 1-2s per ticker on demand).
- **Decision: Robust Capital.com WebSocket**: `_handle_message` is `async` with proper `await broadcast_json()`. Pending tickers queue ensures subscriptions happen even if the WS isn't ready when `set_tickers` is called. 30s recv timeout with ping detects stale connections. Debug logging every 50 price updates.
- **Decision: Card Reorder Animations**: Cards use framer-motion `layout` + `layoutId` for smooth spring animations when re-sorted during live streaming. Transition uses `stiffness: 350, damping: 30`.
- **Decision: Chart Session Backgrounds**: Pre-market (4:00–9:30 ET) has an amber background tint, post-market (16:00–20:00 ET) has a blue tint. Implemented via HistogramSeries on a hidden `bg` price scale with `scaleMargins: {top:0, bottom:0}` to fill the full chart height. `barSpacing: 20` for fat candles, `setVisibleLogicalRange` shows only the last 60 bars.
- **Decision: Chart Session Backgrounds (DST Fix)**: Added dynamic amber (Pre-market) and blue (Post-market) background tints to charts. Refactored the hardcoded ET offset into a dynamic calculation that automatically handles Daylight Savings Time, ensuring the 04:00 AM ET pre-market open aligns correctly with UTC (08:00 AM UTC during DST).
- **Decision: Ultra-Robust Price Level Regex**: Refactored `S_Levels` and `R_Levels` extraction in `ChartPlanView.tsx` and `database.py` to be significantly more resilient. The new regex handles markdown bolding (`**S_Levels**:`), alternative separators (`S-Levels`, `S Levels`), missing brackets, and semicolon delimiters. This ensures compatibility with variant AI formatting observed in specific QCOM and GOOGL cards.
- **Decision: WebSocket Keepalive Fix**: Added proactive heartbeat to `capital_socket.py` (25s interval, independent of data flow). Tracks token age and forces reconnect at 45min (tokens expire at ~60min). Validates ping responses for error/auth-failure payloads instead of treating any response as success. Session TTL in `capital_api.py` increased from 8min to 50min.
- **Decision: Loading Screen**: Minimal sliding status text ("Connecting to database", "Pulling ATR data from Yahoo Finance", etc.) with a pulsing Zap icon and a thin violet progress bar. Each step slides up and the next slides in from below.
- **Decision: Chart Popup Enhancements**: Upgraded `ChartPlanView.tsx` with five major features: (1) Added timeframe pills on the left side of the data source switch (1m, 5m, 30m, 1H, 1D), (2) Expanded the price ladder by default to show trade proximity instantly, (3) Increased modal size to `max-w-6xl` and chart height to `500px` for better visibility, (4) Implemented data-source-aware day count limits (e.g., Yahoo 1m is capped at 7 days, Capital.com 5m is capped at 3 days) to prevent API errors, and (5) Passed risk parameters from the dashboard to display the calculated "Position Size" directly inside the popup.
- **Decision: Widescreen Layout**: Removed `max-w-7xl` cap from the main page layout and widened the chart popup modal to `max-w-[95vw]` so the dashboard and charts utilize the full width of ultrawide monitors.
- **Decision: ETH/RTH Session Toggle**: Added an ETH/RTH pill toggle next to the timeframe pills on the chart popup. Default is ETH (Extended Trading Hours — shows all pre-market, regular, and post-market data). When RTH is selected, bars outside 9:30 AM – 4:00 PM ET are filtered out client-side using a DST-aware UTC-to-ET offset calculation. The toggle uses amber for ETH and emerald for RTH.
## 9. The Data Pipeline
1.  **Load**: Fetch all active tickers from `aw_ticker_notes` in Turso.
2.  **Stream**: Connect to Capital.com WebSockets for live BID/ASK prices.
3.  **Calculate**: Continuously re-calculate the "Tradability Score" (Proximity) for every ticker.
4.  **Sort**: Re-order the UI cards in real-time as prices move.
5.  **Persist**: Economy cards are saved to both local cache and `aw_economy_cards` table on generation.
