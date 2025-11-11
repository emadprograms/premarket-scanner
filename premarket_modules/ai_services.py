import requests
import json
import re
import time
from datetime import datetime
import pandas as pd

# --- Import from our own modules ---
try:
    from . import config
    from .data_processing import (
        get_capital_current_price, 
        get_capital_price_bars, 
        process_premarket_bars_to_summary
    )
    # --- UPDATED: Import the correct DB functions ---
    from .db_utils import (
        get_latest_economy_card_date,
        get_eod_economy_card
    )
    from .ui_components import AppLogger
except ImportError:
    # Handle direct script run vs. module import
    import config
    from data_processing import (
        get_capital_current_price, 
        get_capital_price_bars, 
        process_premarket_bars_to_summary
    )
    # --- UPDATED: Import the correct DB functions ---
    from db_utils import (
        get_latest_economy_card_date,
        get_eod_economy_card
    )
    from ui_components import AppLogger

# ---
# --- Gemini API Call Function (Simple, No KeyManager)
# ---

def call_gemini_api(prompt: str, api_key: str, system_prompt: str, logger: AppLogger, retries: int = 5, delay_seconds: int = 2) -> str | None:
    """
    Calls the Gemini API with a given prompt, system prompt, and API key.
    Includes a simple retry loop per your request (no KeyManager).
    """
    # Use the API_URL from the config file
    api_url = f"{config.API_URL}?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "temperature": 0.5,
            "topK": 1,
            "topP": 1,
            "maxOutputTokens": 8192,
        }
    }

    for attempt in range(retries):
        try:
            logger.log(f"API: Attempt {attempt + 1}/{retries} using key '...{api_key[-4:]}'")
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=90)
            
            if response.status_code == 200:
                response_json = response.json()
                try:
                    text_content = response_json['candidates'][0]['content']['parts'][0]['text']
                    logger.log(f"API: Call successful with key '...{api_key[-4:]}'")
                    return text_content.strip()
                except (KeyError, IndexError, TypeError) as e:
                    logger.log(f"API Error: Could not parse 200 response JSON. Error: {e}")
                    logger.log_code(response_json, 'json')
                    return None # Error in JSON structure, don't retry
            
            logger.log(f"API Error: Status Code {response.status_code} on attempt {attempt + 1}/{retries}")
            logger.log_code(response.text, 'text')
            
            if response.status_code in [429, 500, 503]:
                # Rate limit or server error, wait and retry
                time.sleep(delay_seconds * (2 ** attempt)) # Exponential backoff
            else:
                # Client error (e.g., 400, 403), don't retry
                logger.log("API Error: Client-side error. Aborting retries.")
                return None

        except requests.exceptions.RequestException as e:
            logger.log(f"API Error: RequestException: {e} on attempt {attempt + 1}/{retries}")
            time.sleep(delay_seconds * (2 ** attempt)) # Exponential backoff

    logger.log(f"API Error: Failed to get response after {retries} retries.")
    return None

# ---
# --- AI Orchestrator 1: "Macro Analyst" (Step 0)
# ---

def generate_premarket_economy_card_orchestrator(
    turso_client, 
    premarket_macro_news: str, 
    logger: AppLogger, 
    cst: str, 
    xst: str,
    api_key: str
) -> dict | None:
    """
    Orchestrates the creation of the Pre-Market Economy Card (Step 0).
    """
    logger.log("--- Starting Pre-Market Economy Card Generation (Step 0) ---")
    
    # 1. Get Latest EOD Card Date (Benchmark Date)
    # This uses the new, correct db_utils function
    latest_macro_date = get_latest_economy_card_date(turso_client, logger)
    if not latest_macro_date:
        logger.log("DB Error: Could not get latest_macro_date from 'economy_cards'. Aborting.")
        return None
        
    # 2. Get EOD Card JSON for that date
    # This uses the new, correct db_utils function
    eod_economy_card_dict = get_eod_economy_card(turso_client, latest_macro_date, logger)
    if not eod_economy_card_dict:
        logger.log(f"DB Error: Could not fetch EOD Economy Card for {latest_macro_date}. Aborting.")
        return None
        
    # 3. Fetch Live ETF Data
    logger.log(f"1. Fetching live pre-market data for {len(config.CORE_INTERMARKET_EPICS)} core epics...")
    etf_pm_summaries = []
    for i, epic in enumerate(config.CORE_INTERMARKET_EPICS):
        logger.log(f"   ...Processing {epic}...")
        bid, offer = get_capital_current_price(epic, cst, xst, logger)
        if bid and offer:
            live_price = (bid + offer) / 2
            df_5m = get_capital_price_bars(epic, cst, xst, "MINUTE_5", logger)
            
            if df_5m is not None:
                # Use the NEW upgraded summary function from data_processing.py
                summary = process_premarket_bars_to_summary(epic, df_5m, live_price, logger)
                etf_pm_summaries.append(summary)
        if i < len(config.CORE_INTERMARKET_EPICS) - 1: 
            time.sleep(config.LOOP_DELAY)
    
    etf_pm_summaries_text = "\n\n".join(etf_pm_summaries)
    if not etf_pm_summaries_text:
        logger.log("   ...Warning: Could not fetch any live pre-market data.")

    # 4. Build AI Prompt
    logger.log("2. Building Pre-Market Economy Card Prompt...")
    system_prompt = (
        "You are a macro-economic strategist creating a TACTICAL update for the market open. "
        "You will receive the strategic EOD card, manual news, and LIVE pre-market data (price, vwap, volume profile) for major indices, bonds, commodities, and sectors. "
        "Your task is to synthesize this into a temporary 'Pre-Market Economy Card' reflecting the immediate situation. "
        "Output ONLY the single, valid JSON object."
    )

    today_iso_date = datetime.now(config.US_EASTERN).date().isoformat()
    prompt = f"""
    [DATA]
    1.  **Strategic EOD Card (From {latest_macro_date}):**
        {json.dumps(eod_economy_card_dict, indent=2)}

    2.  **Live Pre-Market Data (Objective Action for {today_iso_date}):**
        (This is the most important data for determining the immediate tactical bias. Analyze it relative to PM VWAP and Value Areas.)
        {etf_pm_summaries_text or "No live pre-market data available."}

    3.  **New Pre-Market Macro News/Events (Manual Input for {today_iso_date}):**
        "{premarket_macro_news or 'No major overnight macro news reported.'}"

    [YOUR TASK]
    Generate the new, temporary "Pre-Market Economy Card" JSON for today, {today_iso_date}.
    
    CRITICAL INSTRUCTIONS:
    1.  **REWRITE TACTICAL FIELDS:** Generate new values for `marketNarrative` and `marketBias` to reflect the immediate pre-market situation.
    2.  **APPEND TO ANALYTICAL FIELDS:** Keep existing EOD text and append a new sub-section (e.g., "**Pre-Market Update:**") to fields like `sectorRotation` and `interMarketAnalysis`.
    3.  **PRESERVE THE HISTORICAL LOG:** Do NOT change `keyActionLog`.
    4.  **UPDATE DATE:** The new JSON you output MUST have a top-level `date` field set to today's date: {today_iso_date}
    5.  **OUTPUT FORMAT:** Output ONLY the single, complete, updated JSON object.
    """

    # 5. Call AI
    logger.log("3. Calling Pre-Market Macro AI...")
    ai_response_text = call_gemini_api(prompt, api_key, system_prompt, logger)

    if not ai_response_text:
        logger.log("Error: No response from Macro AI. Aborting update.")
        return None

    # 6. Parse Response
    logger.log("4. Parsing new Pre-Market Economy Card...")
    json_match = re.search(r"```json\s*([\s\S]+?)\s*```", ai_response_text)
    ai_response_text = json_match.group(1) if json_match else ai_response_text.strip()

    try:
        premarket_economy_card_dict = json.loads(ai_response_text)
        logger.log("--- Success: Pre-Market Economy Card generated. ---")
        return premarket_economy_card_dict
    except json.JSONDecodeError as e:
        logger.log(f"Error processing AI response: {e}")
        logger.log_code(ai_response_text, 'text')
        return None

# ---
# --- AI Orchestrator 2: "Head Trader" (Step 2)
# ---

def run_tactical_screener_orchestrator(
    market_condition: str, 
    economy_card: dict, 
    candidate_data: list[str], 
    api_key: str, 
    logger: AppLogger
) -> str | None:
    """
    Acts as a Head Trader AI to rank the best tactical setups from raw data.
    """
    logger.log("--- Starting Workflow 2: Tactical Screener (Head Trader AI) ---")
    if not candidate_data:
        logger.log("Error: No candidate data provided to the screener.")
        return "Error: No candidate data was provided for ranking."

    economy_card_text = "Not available."
    if economy_card:
        try:
            economy_card_text = json.dumps(economy_card, indent=2)
        except Exception as e:
            logger.log(f"Warning: Could not serialize Economy Card for screener: {e}")
            economy_card_text = str(economy_card)

    all_candidates_text = "\n\n".join(candidate_data)
    logger.log(f"Prepared {len(candidate_data)} candidate summaries for the AI.")

    screener_system_prompt = (
        "You are a 'Head Trader' for a proprietary trading desk. Your job is to find the 'clearest stories' for the Executor. "
        "You will receive the 'Macro Why' (Economy Card), the 'Executor's Focus' (market condition), and a list of 'Candidate Dossiers'. "
        "Each dossier contains the stock's EOD Plan (from the `screener_briefing`) and its 'Live Pre-Market Action' (from the data summary). "
        "Your task is to synthesize all of this information."
        "\n"
        "**Your Ranking Philosophy (CRITICAL):**"
        "1.  **Justification is Everything:** You MUST provide a justification for each pick, explaining *why* it's a clear story. A 'stupid reason' is a failure."
        "2.  **Clarity > 'Best':** Rank based on the 'clearest story' (alignment of Macro + EOD Plan + Live PM Action), not what you guess will be the 'biggest winner'. "
        "3.  **Identify the Plan:** For each pick, you MUST state which plan (Plan_A or Plan_B from the EOD briefing) your analysis supports."
        "4.  **Categorize Setups:** Group your picks by 'Alignment Category' as defined in the prompt. This is not just a 'Top 3' list."
    )

    prompt = f"""
    [PART 1: THE MACRO CONTEXT (The "Macro Why")]
    This is the firm's official view from the Macro Analyst (Step 0).
    {economy_card_text}

    [PART 2: THE EXECUTOR'S FOCUS]
    This is the human trader's qualitative view for the day.
    "{market_condition}"

    [PART 3: THE CANDIDATE DOSSIERS (The "Raw Data")]
    Here are the curated stocks that are at key levels.
    
    {all_candidates_text}

    [YOUR TASK]
    As the Head Trader, analyze all three parts. Your output must be a concise, justified briefing for the Executor.
    Do NOT just list stocks. You MUST group your top picks into the following categories and provide the requested justification.

    **OUTPUT FORMAT (Use this exact Markdown):**

    ### Head Trader's Briefing for the Open

    **Category 1: Full Narrative Alignment (High Conviction Stories)**
    (Setups where the 'Macro Why', 'Executor's Focus', and 'Live PM Action' are all aligned with the EOD Plan.)

    * **1. Ticker: [TICKER]**
        * **Selected Plan:** [Plan_A or Plan_B from the EOD Briefing]
        * **Justification:** [Your analysis. e.g., "This is the clearest story. The Macro 'Bearish' bias and 'Lagging XLI' theme perfectly match the EOD 'Short Resistance' plan. The live PM action confirms this, showing weakness below its PM VWAP, signaling a high-conviction short setup."]

    **Category 2: Primary Bias Alignment (Confirmation Setups)**
    (Setups that align with the *primary* Macro Bias (e.g., Bearish) but are not in the main "story" sector.)

    * **1. Ticker: [TICKER]**
        * **Selected Plan:** [Plan_A or Plan_B]
        * **Justification:** [e.g., "This SHOP setup aligns with the macro 'Bearish' bias. While not in a lagging sector, its EOD 'Short' plan is being confirmed by live action (trending near PML). This may be a cleaner entry."]

    **Category 3: Narrative Misalignment (Contrarian / Relative Strength Setups)**
    (Setups that *fight* the macro bias but are supported by a clear secondary narrative, like relative strength.)

    * **1. Ticker: [TICKER]**
        * **Selected Plan:** [Plan_A or Plan_B]
        * **Justification:** [e.g., "This XLP setup is a high-conviction *long*, despite the 'Bearish' macro. The Macro Card *itself* identified XLP as a 'Leading Sector' (flight to safety). The live PM action confirms this, showing strength above its PM VWAP."]
    
    *(Only include categories if you find setups that match.)*
    """
    
    logger.log("Calling Head Trader AI to rank setups...")
    ai_response = call_gemini_api(prompt, api_key, screener_system_prompt, logger)

    if not ai_response:
        logger.log("Error: The screener AI did not return a response.")
        return "The AI screener failed to generate a ranking. Please check the logs."
        
    logger.log("--- Tactical Screener Complete ---")
    return ai_response