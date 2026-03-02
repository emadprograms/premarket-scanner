# Gemini Updates

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
