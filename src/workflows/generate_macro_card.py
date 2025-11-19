# src/workflows/generate_macro_card.py

import json
import re
import time
from datetime import datetime, timezone

# Assuming these imports are correct based on the new structure
from src.config.constants import CORE_INTERMARKET_EPICS, LOOP_DELAY, US_EASTERN
from src.external_services.database.connection import create_turso_client
from src.external_services.database.queries import get_latest_economy_card_date, get_eod_economy_card
from src.external_services.broker_api.market_data import get_capital_current_price, get_capital_price_bars
from src.core_trading_logic.technical_indicators import process_premarket_bars_to_summary
from src.external_services.ai_service.llm_calls import call_gemini_api

def generate_premarket_economy_card(
    premarket_macro_news: str,
    cst: str,
    xst: str,
    api_key: str
) -> tuple[dict | None, str | None, list[str]]:
    """
    Orchestrates the entire process of building the Pre-Market Economy Card.
    This function DOES NOT log to the UI. Instead, it collects log messages
    and returns them as a list for the UI to process and display.
    
    Returns:
        - A dictionary representing the economy card, or None on failure.
        - An error message string, or None on success.
        - A list of all log messages generated during the process.
    """
    log_messages = []

    def log(message: str):
        """A local helper to append timestamped messages to the list."""
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        log_messages.append(f"**{ts}Z:** {message}")

    log("--- Starting Pre-Market Economy Card Generation ---")
    
    # NOTE: You would need to update your helper functions to accept this `log` function
    # instead of an AppLogger object. For example:
    # `def create_turso_client(log_func): ...`
    # For now, we will assume they have been updated.
    
    client = create_turso_client(log)
    if not client:
        log("Workflow aborted: Could not create database client.")
        return None, "No DB connection.", log_messages

    latest_macro_date = get_latest_economy_card_date(client, log)
    if not latest_macro_date:
        log("Workflow aborted: Could not find any macro dates in 'economy_cards' table.")
        return None, "No macro dates found in DB.", log_messages

    eod_card = get_eod_economy_card(client, latest_macro_date, log)
    if not eod_card:
        log(f"Workflow aborted: Could not find EOD Card for date {latest_macro_date}.")
        return None, f"No EOD Card for date {latest_macro_date}.", log_messages

    log(f"Fetching live pre-market data for {len(CORE_INTERMARKET_EPICS)} core epics...")
    summaries = []
    for i, epic in enumerate(CORE_INTERMARKET_EPICS):
        log(f"Processing epic: {epic} ({i+1}/{len(CORE_INTERMARKET_EPICS)})")
        bid, offer = get_capital_current_price(epic, cst, xst, log)
        if bid and offer:
            live_price = (bid + offer) / 2
            df_pm = get_capital_price_bars(epic, cst, xst, "MINUTE_5", log)
            if df_pm is not None and not df_pm.empty:
                summary = process_premarket_bars_to_summary(epic, df_pm, live_price, log)
                summaries.append(summary)
            else:
                log(f"No pre-market bars for {epic} to summarize.")
        else:
            log(f"Could not get live price for {epic}. Skipping.")
        
        if i < len(CORE_INTERMARKET_EPICS) - 1:
            time.sleep(LOOP_DELAY)
            
    summaries_text = "\n\n".join(summaries)

    log("Building prompt for AI...")
    prompt = f"""
[CONTEXT]
Today's Date: {datetime.now(US_EASTERN).date().isoformat()}

[DATASET 1: STRATEGIC EOD CARD (from {latest_macro_date})]
{json.dumps(eod_card, indent=2)}

[DATASET 2: LIVE PRE-MARKET DATA (collected just now)]
{summaries_text or "No live pre-market data was available for any core epics."}

[DATASET 3: MANUAL OVERNIGHT NEWS/EVENTS]
"{premarket_macro_news or "No major overnight macro news was reported."}"

[YOUR TASK]
You are a macro-economic strategist. Synthesize all three datasets into a new, temporary "Pre-Market Economy Card" for today. This card provides the tactical bias for the market open. The output must be a single, valid JSON object and nothing else.
    """.strip()

    system_prompt = (
        "You are an expert financial analyst. Your sole purpose is to generate a JSON object based on the user's request. "
        "Do not include any conversational text, pleasantries, or markdown formatting like ```"
    )

    log("-- Calling Pre-Market Macro AI --")
    # Assume call_gemini_api is also updated to return its internal logs
    ai_response_text, ai_logs = call_gemini_api(prompt, api_key, system_prompt)
    log_messages.extend(ai_logs) # Add logs from the AI call to our main list

    if not ai_response_text:
        log("Workflow failed: Gemini API did not return any text.")
        return None, "Gemini API did not return any text (empty or error).", log_messages

    log("-- Parsing new Pre-Market Economy Card... --")
    json_match = re.search(r"```json\s*([\s\S]+?)\s*```", ai_response_text)
    payload = json_match.group(1) if json_match else ai_response_text.strip()
    try:
        macro_card = json.loads(payload)
        log("Success: Pre-Market Economy Card generated and parsed.")
        return macro_card, None, log_messages
    except json.JSONDecodeError as e:
        log(f"Fatal Error: Could not parse AI response as JSON. Error: {e}")
        log("--- RAW AI RESPONSE START ---")
        log(ai_response_text)
        log("--- RAW AI RESPONSE END ---")
        return None, "Gemini returned a response that could not be parsed as JSON.", log_messages
