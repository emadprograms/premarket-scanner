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
| `aw_company_cards` | Per-ticker company analysis cards | `ticker`, `date`, `company_card_json` |
| `deep_dive_cards` | Live deep-dive analysis cards | `ticker`, `date`, `timestamp`, `card_json` |
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

### Economy Card Persistence
Economy cards are saved in two places:
1. **Local JSON cache**: `data/economy_card_cache.json` (fast read for status checks)
2. **Turso DB**: `aw_economy_cards` table (persistent, used by Archive Room)

Both are written by `macro.py` when a macro analysis completes.

## 7. Frontend Architecture

### Key Files
| File | Role |
|---|---|
| `frontend/src/app/page.tsx` | Main scanner view (proximity engine, ranking feed) |
| `frontend/src/lib/context.tsx` | `MissionProvider` — global settings & system status polling |
| `frontend/src/lib/api.ts` | Axios API client (base URL auto-detection) |
| `frontend/src/lib/socket.ts` | WebSocket client for log streaming |
| `frontend/src/components/layout/Shell.tsx` | App shell with sidebar nav, header, status bar |
| `frontend/src/components/layout/CardEditorView.tsx` | Archive Room — economy/company card viewer |
| `frontend/src/components/layout/EconomyCardView.tsx` | Economy card renderer |
| `frontend/src/components/layout/CompanyCardView.tsx` | Company card renderer |
| `frontend/src/components/layout/MissionControl.tsx` | Settings panel (mode, dates, thresholds) |

### Data Shape Contract (Archive)
The archive API returns cards with these exact field names — the frontend components depend on them:
- Economy: `{ date, economy_card_json: {...} }`
- Company: `{ ticker, date, company_card_json: {...} }`

## 8. Evolution & Decision Log (Troubleshooting & Core Reasoning)
- **Decision: Removal of AI**: We removed all LLM-based narrative generation because it introduced latency and hallucinations. The "Senior Desk Lead" identity now manifests as mathematical precision in ranking, not verbal analysis.
- **Decision: Proximity over Percentage**: We moved to ATR-normalized proximity because a $1 move on a $100 stock is not the same as a $1 move on a $500 stock. This ensures the "Tradability" ranking is volatility-aware.
- **Decision: Backend Host Binding**: Changed backend binding from `127.0.0.1` to `0.0.0.0` to resolve connectivity issues where the frontend couldn't reach the backend due to IPv4/IPv6 resolution ambiguity.
- **Decision: Robust API Base URL**: Updated `frontend/src/lib/api.ts` to dynamically detect the hostname. Crucially, it now forces `127.0.0.1` when `localhost` is detected to bypass macOS IPv6 resolution issues (where `localhost` resolves to `::1` but the backend is only listening on IPv4).
- **Decision: CORS Simplification**: Removed `allow_credentials=True` from `backend/main.py` CORS middleware. Standard browser security prevents `allow_origins=["*"]` from working with credentials, which often causes silent `Network Errors` during preflight (OPTIONS) requests.
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

## 9. The Data Pipeline
1.  **Load**: Fetch all active tickers from `aw_ticker_notes` in Turso.
2.  **Stream**: Connect to Capital.com WebSockets for live BID/ASK prices.
3.  **Calculate**: Continuously re-calculate the "Tradability Score" (Proximity) for every ticker.
4.  **Sort**: Re-order the UI cards in real-time as prices move.
5.  **Persist**: Economy cards are saved to both local cache and `aw_economy_cards` table on generation.
