# Gemini Updates

## 2026-03-02 Updates

* **Position Sizing with Bid/Ask Spread:**
  * Added dynamic bid/ask mapping to the real-time Capital.com WebSocket pipeline.
  * Corrected Position Sizing mathematical logic:
    * **Long Setups (Support):** Calculations and entry execution are mapped to the **Ask** price.
    * **Short Setups (Resistance):** Calculations and entry execution are mapped to the **Bid** price.
  * Extracted the dynamic `entryPrice` calculation in the card loop so the UI now accurately shows "Live Ask" or "Live Bid" alongside the respective price used for calculating the share size layout.
  * Implemented an advanced search loop for invalidation data to pick the number closest to the live price, effectively bypassing bullet point indices rendering incorrect calculations (fixed edge cases for NVDA/MSFT).

* **Premium UI Polish:**
  * Replaced native browser number spinners (scrollbars) with custom Framer/Lucide modern chevron up/down steppers for Capital and Risk inputs.
  * Attached sleek, dark-mode tooltips with explicit descriptions for `Capital`, `Risk`, and `Connect` icons inside the `Shell.tsx` scanner header.
