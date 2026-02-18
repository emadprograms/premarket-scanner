from __future__ import annotations
import json
import re
from datetime import date
from backend.engine.utils import AppLogger
from backend.engine.key_manager import KeyManager

# --- DEFAULT MACRO TEMPLATE (Narrative Compliant) ---
DEFAULT_ECONOMY_CARD_JSON = """
{
    "marketNarrative": "Initializing Macro Context...",
    "marketBias": "Neutral",
    "keyEconomicEvents": {
        "last_24h": "Summary of key past events.",
        "next_24h": "Summary of key upcoming events."
    },
    "sectorRotation": {
        "leadingSectors": [],
        "laggingSectors": [],
        "rotationAnalysis": "Initializing sector flow analysis..."
    },
    "indexAnalysis": {
        "pattern": "None",
        "SPY": "Initializing levels...",
        "QQQ": "Initializing levels..."
    },
    "interMarketAnalysis": {
        "bonds": "Analysis of TLT/Yields.",
        "commodities": "Analysis of Oil/Gold.",
        "currencies": "Analysis of DXY.",
        "crypto": "Analysis of BTC."
    },
    "marketInternals": {
        "volatility": "Analysis of VIX and Breadth."
    },
    "todaysAction": "Log of today's primary market outcome."
}
"""

def summarize_rolling_log(log: list[dict], logger: AppLogger) -> str:
    """
    Summarizes a long list of key actions into a concise 'Macro Arc'.
    Maintains Act 1 (Origins), Middle (Transformation), and Recent (Regime).
    """
    if not log:
        return "No prior market action logged."
    
    if len(log) <= 7:
        return json.dumps(log, indent=2)
    
    # Structural Summarization (preserving the Arc)
    start_point = log[:2]
    middle_point = log[len(log)//2 : len(log)//2 + 1]
    recent_regime = log[-4:]
    
    summary = [
        "### HISTORICAL MACRO ARC (Summarized for Context) ###",
        "Regime Origins:",
        *[f"- {i.get('date')}: {i.get('action')}" for i in start_point],
        "\nMid-Cycle Shift:",
        *[f"- {i.get('date')}: {i.get('action')}" for i in middle_point],
        "\nRecent Regime (The Immediate Anchor):",
        *[f"- {i.get('date')}: {i.get('action')}" for i in recent_regime],
        "### END HISTORICAL ARC ###"
    ]
    return "\n".join(summary)

def generate_economy_card_prompt(
    eod_card: dict,
    etf_structures: list,
    news_input: str,
    analysis_date_str: str,
    logger: AppLogger,
    rolling_log: list[dict] = None,
    scaling_notes: str = "",
    pre_summarized_context: str = None,
    sentiment_data: dict = None
) -> tuple[str, str]:
    """
    Constructs the 'Market Historian' System Prompt.
    Returns: (prompt, system_prompt)
    """
    
    # Defaults
    if rolling_log is None: rolling_log = []
    
    # --- V8 SINGLE PATH HISTORY LOGIC ---
    summarized_log = None
    clean_eod = eod_card.copy() if eod_card else {}

    if pre_summarized_context:
        summarized_log = f"### HISTORICAL MACRO ARC (AI Summary) ###\n{pre_summarized_context}\n### END HISTORICAL ARC ###"
        if "keyActionLog" in clean_eod:
            del clean_eod["keyActionLog"]

    # --- 1. Construct System Prompt (The Senior Market Analyst) ---
    system_prompt = (
        "You are a Senior Market Analyst and Trading Desk Lead. Your mission is to provide a high-level 'Executive Briefing' of the market session by synthesizing global news and price data.\n\n"
        
        "**WRITING STYLE GUIDELINES:**\n"
        "1. **Professional & Accessible:** Sound like a professional trader or Bloomberg analyst. Avoid heavy technical jargon or academic tone.\n"
        "2. **The 'Why':** Explain the connection between the major News (Trigger) and the Price Action (Verdict). Did the news surprise the market? Was it accepted or rejected?\n"
        "3. **Narrative Clarity:** Instead of technical terms like 'Committed/Desperate' or 'Closing the Ledger', use descriptive professional language such as 'Institutional Support,' 'Aggressive Selling,' 'Price discovery,' or 'Risk-off rotation.'\n"
        "4. **Synthesis:** Combine bond yields, currencies, and sector flow into a single cohesive story that explains the current market regime.\n\n"

        "**DATA INTEGRITY PROTOCOL (CRITICAL):**\n"
        "- **No Hallucinations:** Only analyze the data provided in the sections below.\n"
        "- **Acknowledge Missing Data:** If a ticker or sector mentioned in the schema (e.g., QQQ, Bonds, VIX) is missing from the input data, do NOT assume its state. Explicitly state 'Data not provided' or 'Ticker missing from scan' in the relevant field.\n"
        "- **Focus on Evidence:** Your narrative must be grounded in the provided price action and news. If the evidence is thin, be neutral and state that the trend is unclear due to lack of participation.\n\n"

        "**YOUR OUTPUT: A PROFESSIONAL BRIEFING**\n"
        "Produce a cohesive `marketNarrative` paragraph that explains current market dynamics. It should be punchy, insightful, and easy for a trader to process in 30 seconds.\n"
    )

    # --- 2. Construct Sections ---
    history_section = ""
    if summarized_log:
        history_section = f"\n    [2. Log of Recent Key Actions (Historical Context)]\n    {summarized_log}\n"

    # --- 3. Construct Main Prompt ---
    prompt = f"""
    [1. Previous Closing Context (The Anchor)]
    {json.dumps(clean_eod, indent=2)}
    {history_section}
    [3. Raw Market News (THE TRIGGER)]
    {news_input or "No news provided."}
    
    [4. Automated Sentiment Analysis (THE TONE)]
    {json.dumps(sentiment_data, indent=2) if sentiment_data else "No sentiment analysis provided."}

    [5. Core Indices Structure (THE VERDICT)]
    {scaling_notes or ""}
    {json.dumps(etf_structures, indent=2)}

    [Your Task for {analysis_date_str}]
    Synthesize the above data into a Global Economy Card.
    
    - **marketNarrative**: A rich, paragraph-length executive summary. Explain the 'Why' using professional financial reasoning, focusing on institutional flow and market sentiment.
    - **marketBias**: Bullish/Bearish/Neutral/Volatile.
    - **indexAnalysis/sectorRotation**: Analyze the flow of money.
    - **todaysAction**: A single, punchy sentence for the log.

    [Output Format Constraint]
    Output ONLY a single, valid JSON object matching the schema below:
    
    {{
        "marketNarrative": "The story of the session...",
        "marketBias": "Neutral",
        "keyEconomicEvents": {{
            "last_24h": "...",
            "next_24h": "..."
        }},
        "sectorRotation": {{
            "leadingSectors": [],
            "laggingSectors": [],
            "rotationAnalysis": "..."
        }},
        "indexAnalysis": {{
            "pattern": "U-Shape / Spike / ...",
            "SPY": "...",
            "QQQ": "..."
        }},
        "interMarketAnalysis": {{
            "bonds": "Analysis of TLT/Yields.",
            "commodities": "Analysis of Oil/Gold.",
            "currencies": "Analysis of DXY.",
            "crypto": "Analysis of BTC."
        }},
        "marketInternals": {{
            "volatility": "Analysis of VIX."
        }},
        "todaysAction": "A single sentence summary."
    }}
    """
    
    return prompt, system_prompt
