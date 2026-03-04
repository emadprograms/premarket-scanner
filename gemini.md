# Gemini Updates

## 2026-03-04 Updates

* **Capital.com WebSocket Event Loop Fix (Critical):**
  * Diagnosed that `create_capital_session_v2()` uses synchronous `requests.post()`, which **blocked the entire FastAPI async event loop** for up to 15 seconds per call — making the backend completely unresponsive to frontend HTTP requests during Capital.com auth.
  * Wrapped all calls to `create_capital_session_v2()` with `asyncio.to_thread()` in both `capital_socket.py` and `system.py` so they run in the thread pool without blocking.
  * The `/api/system/status` endpoint (polled by the frontend every 10-30s) was also calling Capital auth and DB checks synchronously — both now run via `asyncio.to_thread()`.

* **Token Cache Expiry (Session Staleness Fix):**
  * Capital.com session tokens were cached indefinitely (`_CAPITAL_SESSION_CACHE`), causing the WS to reconnect endlessly with stale tokens after ~10 minutes.
  * Added `_SESSION_TTL_SECONDS = 480` (8 minutes) TTL to the cache. Tokens are now automatically refreshed before Capital.com invalidates them (~10 min).
  * On WS ping failure, `clear_capital_session()` is called to force a fresh token on the next reconnect attempt.

* **Capital WebSocket Idle Connection Prevention:**
  * The WS `_run_loop` now checks if tickers are set before attempting to connect. When the backend starts without any scan request, it idles quietly instead of repeatedly connecting/disconnecting to Capital.com with no subscriptions.
  * Replaced WebSocket protocol-level `ping()` with Capital.com's expected application-level JSON ping (with `cst`/`securityToken` and `correlationId`).
  * Added `correlationId` to all subscription/unsubscription/ping messages matching the Capital.com API contract.
  * Added exponential backoff (5s → 10s → 20s → 60s max) on reconnection failures, reset on successful connection.

* **Frontend API URL Resolution (Vercel Deployment Fix):**
  * Fixed `getBaseUrl()` in `api.ts` — the fallback was appending `:8000` to the Vercel hostname (e.g., `https://your-app.vercel.app:8000`), which doesn't exist.
  * Added explicit support for GitHub Codespaces port rewriting.
  * On production domains without `NEXT_PUBLIC_API_URL`, the frontend now logs a clear error message instead of silently failing.

* **CORS & Deployment Hardening:**
  * Added `expose_headers=["*"]` and explicit `allow_credentials=False` to the CORS middleware for proper cross-origin behavior with Vercel.
  * Updated `backend-runner.yml` to print the `NEXT_PUBLIC_API_URL` setup instructions in the GitHub Actions workflow log.

## 2026-03-02 Updates

* **Position Sizing with Bid/Ask Spread:**
  * Added dynamic bid/ask mapping to the real-time Capital.com WebSocket pipeline.
  * Corrected Position Sizing mathematical logic:
    * **Long Setups (Support):** Calculations and entry execution are mapped to the **Ask** price.
    * **Short Setups (Resistance):** Calculations and entry execution are mapped to the **Bid** price.
  * Refactored the `Live Price` dashboard display logic so it evaluates the actual backend Plan logic (`isLongTrade`) to label "Live Ask" or "Live Bid", successfully decoupling this choice from the structural trend (Above/Below) indicator.
  * Implemented an advanced search loop for invalidation data to pick the number closest to the live price, effectively bypassing bullet point indices rendering incorrect calculations (fixed edge cases for NVDA/MSFT).

* **Position Sizing with Spread Constraint (Risk Clamp):**
  * Updated position size equation in both `page.tsx` and `audit_size.py` to handle slippage edge cases inherently found in dynamic environments.
  * Extracted directional distance logic for Longs (Ask - Invalidation) and Shorts (Invalidation - Bid).
  * **Breached Setup UI Support:** If the directional distance drops below `0` (indicating the live entry has broken the stop-loss plan), the dashboard card now dynamically grayscales itself (`opacity-40 grayscale`) to visibly alert the user that the setup is invalid and requires updating. 
  * **Breached Ranking Exclusion:** Moved the `isBreached` evaluation upstream into the dashboard `useMemo` map, successfully isolating these cards and sinking them visually to the absolute bottom of the proximity ranking, removing them from viable target focus.
  * The risk distance is now strictly clamped to `max(actualDistance, spread)`, ensuring that if a stop-loss is placed inside the spread (or triggers immediately as a breached setup), the risk shares natively limit to the maximum bid-ask slippage. This directly prevents over-leveraged math (such as suggesting extremely high share volumes if the invalidation distance is technically negative or mere cents).

* **Premium UI Polish:**
  * Replaced native browser number spinners (scrollbars) with custom Framer/Lucide modern chevron up/down steppers for Capital and Risk inputs.
  * Attached sleek, dark-mode tooltips with explicit descriptions for `Capital`, `Risk`, and `Connect` icons inside the `Shell.tsx` scanner header.
