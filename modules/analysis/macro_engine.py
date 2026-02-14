from __future__ import annotations
import json
import re
from datetime import date
from modules.utils import AppLogger
from modules.key_manager import KeyManager
from modules.gemini import call_gemini_with_rotation

def update_economy_card(
    previous_economy_card_dict: dict,
    daily_market_news: str,
    etf_summaries: list,
    model_name: str,
    key_manager: KeyManager,
    logger: AppLogger,
    trade_date_str: str
) -> str | None:
    """
    Updates the Economy Card using the User's strict 60/40 Synthesis Logic.
    Returns: JSON string of the updated card.
    """
    
    # 1. Prepare Context
    recent_log_entries = previous_economy_card_dict.get('keyActionLog', [])

    # --- FIX: Rebuilt System Prompt ---
    system_prompt = (
        "You are a macro-economic strategist. Your task is to update the *entire* global 'Economy Card' JSON. "
        "Your primary goal is a **two-part synthesis**: "
        "1. **Synthesize the narrative ('Why')** from the `[Raw Market News]` input. DO NOT expect a pre-written wrap; you must decode the raw headlines yourself. "
        "2. Find the **level-based evidence ('How')** in the `[Key ETF Summaries]` (Impact Context Cards) to **prove or disprove** that narrative. "
        "You must continue the story from the previous card, evaluating how today's data confirms, contradicts, or changes the established trend."
    )
    
    # --- FIX: Rebuilt Main Prompt with two-part synthesis logic ---
    prompt = f"""
    [Previous Day's Economy Card (Read-Only)]
    (This is the established macro context. You must read this first.)
    {json.dumps(previous_economy_card_dict, indent=2)}

    [Log of Recent Key Actions (Read-Only)]
    (This is the day-by-day story so far. Use this for context.)
    {json.dumps(recent_log_entries, indent=2)}

    [Raw Market News Input (The 'Why' / Narrative Source)]
    (This contains RAW news headlines and snippets. You must synthesize the narrative 'Story' yourself from this data.)
    {daily_market_news or "No raw market news was provided."}

    [Key ETF Summaries (The 'How' / IMPACT CONTEXT CARDS)]
    (This is the quantitative, level-based 'proof'. Use the 'Value Migration Log' and 'Impact Levels' for SPY, QQQ, etc. to confirm the narrative.)
    {json.dumps(etf_summaries, indent=2)}

    [Your Task for {trade_date_str}]
    Based on *all* the information above, generate a new, complete JSON object by following
    these rules to fill the template below.

    **Master Rule (Weighted Synthesis - 60/40 Logic):**
    Your primary goal is to determine the **governing short-term trend** (the "story" from the last 3-5 days) and then evaluate if **today's action** (the new data) *confirms, contradicts, or changes* that trend.

    1.  **Identify the "Governing Trend" (The 60% Weight):**
        * First, read the `marketBias` and `indexAnalysis` from the `[Previous Day's Card]` and the `[Log of Recent Key Actions]`.
        * This gives you the established narrative. (e.g., "SPY is in a 3-day bearish channel, failing at $450.")

    2.  **Evaluate "Today's Data" (The 40% Weight):**
        * **Synthesize BOTH data sources.** Decode the `[Raw Market News Input]` for the narrative (e.g., "breadth was weak").
        * **Then, verify** that narrative using the `[Key ETF Summaries]` (e.g., "This is confirmed: IWM and DIA broke their ORLs and closed below VWAP, while QQQ held its VAL.").
        * The *quality* of the move (proven by levels) is more important than the direction.

    3.  **Synthesize (The New `marketBias` and `marketNarrative`):**
        * Your `marketNarrative` must explain this two-part synthesis.
        * **If Today's Data CONFIRMS the trend:** The `marketBias` is strengthened. (e.g., "A low-volume rally into resistance, confirmed by IWM closing below its POC, *confirms* the bearish trend. Bias remains `Bearish`.")
        * **If Today's Data is just NOISE:** The `marketBias` is unchanged.
        * **If Today's Data CHANGES the trend:** The `marketBias` can flip. This *must* be a high-conviction event, supported by *both* the narrative and strong level-based breaks in the ETFs (e.g., "SPY broke *above* the $450 channel on high volume, with QQQ and IWM also closing above their VAH. The governing trend is now changing. Bias moves to `Neutral` or `Bullish`.")

    **Detailed "Story-Building" Rules:**

    * **`keyEconomicEvents`:** Populate this *directly* by synthesizing the "REAR VIEW" and "COMING UP" events found in the `[Raw Market News Input]`.
    * **`indexAnalysis` (Story-Building with 3-Act Logic):**
        * Read the `indexAnalysis` from the `[Previous Day's Card]`.
        * Using today's synthesized narrative *and* the specific `sessions` data from the 20 ETFs, write the **new, updated** analysis.
        * **You MUST analyze the 'Session Arc' (Pre -> RTH -> Post):**
        * (e.g., "SPY showed a 'fake-out' gap in Pre-Market, but RTH invalidated it by closing below VWAP. This weakness was **confirmed** by IWM failing to hold its Pre-Market low.").
        * **Cite level-based evidence.** (e.g., "QQQ ended the RTH session below its POC ($385.50), signaling a failed rally...").
    * **`sectorRotation` (Story-Building with 3-Act Logic):**
        * Read the `sectorRotation` analysis from the `[Previous Day's Card]`.
        * Using today's **3-Session ETF data** (XLK, XLF, etc.), update the `leadingSectors`, `laggingSectors`, and `rotationAnalysis`.
        * **Analyze the Session Arc:** (e.g., "Tech (XLK) gapped up in Pre-Market but saw heavy profit-taking in RTH, **closing below its VAH ($303.78)**, moving it to lagging...").
    * **`interMarketAnalysis` (Story-Building with 3-Act Logic):**
        * Read the `interMarketAnalysis` from the `[Previous Day's Card]`.
        * Using the `[Raw Market News Input]` *and* the **3-Session Impact Data** for TLT, GLD, UUP, **continue the narrative**.
        * **Analyze the Session Arc:** (e.g., "Bonds (TLT) *continued* their decline, gaping down in Act I and confirming weakness in Act II by **breaking below VAL ($89.60)**..." or "The Dollar (UUP) was choppy, **crossing VWAP ($28.23) multiple times** during RTH...").
    * **`todaysAction` (The Log):** Create a *new, single log entry* for today's macro action, referencing both the synthesized narrative and key ETF level interactions.

    **MISSING DATA RULE (CRITICAL):**
    * If `[Raw Market News Input]` or `[Key ETF Summaries]` are missing, empty, or clearly irrelevant, you **MUST** state this in the relevant analytical fields.
    * **DO NOT** silently copy yesterday's data.
    * *(Example: `indexAnalysis.SPY`: "No new ETF data was provided to update the analysis.")*

    [Output Format Constraint]
    Output ONLY a single, valid JSON object in this exact format. **You must populate every single field.**

    {{
      "marketNarrative": "Your new high-level narrative (based on the Master Rule).",
      "marketBias": "Your new bias (e.g., 'Bullish', 'Bearish', 'Neutral') (based on the Master Rule).",
      "keyEconomicEvents": {{
        "last_24h": "Your summary of past events synthesized from the raw news.",
        "next_24h": "Your summary of upcoming events synthesized from the raw news."
      }},
      "sectorRotation": {{
        "leadingSectors": ["List", "of", "leading", "sectors"],
        "laggingSectors": ["List", "of", "lagging", "sectors"],
        "rotationAnalysis": "Your 'Story-Building' analysis of the sector rotation, citing level-based evidence."
      }},
      "indexAnalysis": {{
        "pattern": "Your new high-level summary of the *main indices* pattern.",
        "SPY": "Your 'Story-Building' analysis of SPY, citing level-based evidence (VWAP, POC, VAH/VAL).",
        "QQQ": "Your 'Story-Building' analysis of QQQ, citing level-based evidence (VWAP, POC, VAH/VAL)."
      }},
      "interMarketAnalysis": {{
        "bonds": "Your 'Story-Building' analysis of TLT/bonds (citing Market Wrap and level-based data).",
        "commodities": "Your 'Story-Building' analysis of GLD/Oil (citing Market Wrap and level-based data).",
        "currencies": "Your 'Story-Building' analysis of UUP/Dollar (citing Market Wrap and level-based data).",
        "crypto": "Your 'Story-Building' analysis of Crypto/BTC (citing level-based data)."
      }},
      "marketInternals": {{
        "volatility": "Your analysis of VIX/volatility."
      }},
      "todaysAction": "A single, detailed log entry for *only* today's macro action, referencing key ETFs and news."
    }}
    """

    logger.log("3. Calling Macro Strategist AI...")
    
    ai_response_text, error = call_gemini_with_rotation(prompt, system_prompt, logger, model_name, key_manager)
    if not ai_response_text:
        logger.log(f"Error: No response from AI for economy card update. Details: {error}")
        return None

    logger.log("4. Received new Economy Card. Parsing and validating...")
    json_match = re.search(r"```json\s*([\s\S]+?)\s*```", ai_response_text)
    if json_match:
        ai_response_text = json_match.group(1)
    
    try:
        # --- FIX: We are now parsing the AI's *new* output ---
        ai_data = json.loads(ai_response_text)
        
        # --- FIX: Extract the 'todaysAction' ---
        new_action = ai_data.pop("todaysAction", None)
        
        if not new_action:
            logger.log("Error: AI response is missing required fields.")
            return None

        # --- FIX: Rebuild the full card in Python ---
        final_card = previous_economy_card_dict.copy()
        
        # 2. **Deeply update** the card with the new AI data
        def deep_update(d, u):
            for k, v in u.items():
                if isinstance(v, dict):
                    d[k] = deep_update(d.get(k, {}), v)
                else:
                    d[k] = v
            return d
            
        final_card = deep_update(final_card, ai_data)
        
        # 3. Programmatically append to the log
        if "keyActionLog" not in final_card or not isinstance(final_card['keyActionLog'], list):
            final_card['keyActionLog'] = []
        
        # --- Remove the old, deprecated 'marketKeyAction' field if it exists ---
        if 'marketKeyAction' in final_card:
            del final_card['marketKeyAction']

        if not any(entry.get('date') == trade_date_str for entry in final_card['keyActionLog']):
            final_card['keyActionLog'].append({
                "date": trade_date_str,
                "action": new_action
            })
        else:
            logger.log("   ...Log entry for this date already exists. Overwriting.")
            for i, entry in enumerate(final_card['keyActionLog']):
                if entry.get('date') == trade_date_str:
                    final_card['keyActionLog'][i] = {
                        "date": trade_date_str,
                        "action": new_action
                    }
                    break

        logger.log("--- Success: Economy Card generation complete! ---")
        return json.dumps(final_card, indent=4)
    except Exception as e:
        logger.log(f"Error parsing AI response: {e}")
        return None
