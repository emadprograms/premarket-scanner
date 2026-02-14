from __future__ import annotations
import json
import re
from datetime import date
from modules.utils import AppLogger
from modules.key_manager import KeyManager

# --- DEFAULT MACRO TEMPLATE (Masterclass Compliant) ---
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
    "todaysAction": "Log of today's primary market outcome.",
    "masterclass": {
        "confidence": "Neutral",
        "screener_briefing": "Setup_Bias: Neutral\\nJustification: Initializing.\\nCatalyst: None\\nPattern: None\\nPlan_A: None\\nPlan_A_Level: 0.0\\nPlan_B: None\\nPlan_B_Level: 0.0\\nS_Levels: []\\nR_Levels: []",
        "basicContext": {
            "priceTrend": "Neutral",
            "recentCatalyst": "None"
        },
        "technicalStructure": {
            "majorSupport": "None",
            "majorResistance": "None",
            "pattern": "None",
            "volumeMomentum": "None"
        },
        "behavioralSentiment": {
            "buyerVsSeller": "Neutral",
            "emotionalTone": "Neutral",
            "newsReaction": "Neutral"
        },
        "marketOutlook": {
            "planName": "None",
            "knownParticipant": "None",
            "expectedParticipant": "None",
            "trigger": "None",
            "invalidation": "None"
        }
    }
}
"""

def generate_economy_card_prompt(
    eod_card: dict,
    etf_structures: list,
    news_input: str,
    analysis_date_str: str,
    logger: AppLogger,
    rolling_log: list[dict] = None
) -> tuple[str, str]:
    """
    Constructs the 'Masterclass' System Prompt and Main Prompt for the Economy Card.
    Returns: (prompt, system_prompt)
    """
    
    # Defaults
    if rolling_log is None: rolling_log = []

    # --- 1. Construct System Prompt (The Macro Strategist Persona) ---
    system_prompt = (
        "You are an expert Global Macro Strategist. Your job is to strictly follow a 'Weighted Synthesis' logic to update the Global Economy Card. "
        "You must adhere to the following 3 Core Rules:\n\n"
        "**RULE 1: The '60/40 Synthesis' Rule**\n"
        "   - **60% Weight (Governing Trend):** The existing 'marketBias' from the Previous Card is your anchor. Trends are heavy and hard to turn.\n"
        "   - **40% Weight (Today's Data):** The combination of News + ETF Levels.\n"
        "   - **Decision Logic:**\n"
        "       * *Confirmation:* If Today's Data matches the Trend -> Bias Confidence INCREASES.\n"
        "       * *Noise:* If Today's Data is weak/mixed -> Bias STAYS THE SAME.\n"
        "       * *Reversal:* ONLY if Today's Data is High Conviction (e.g., SPY breaks major level + Confirming News) -> Bias FLIPS.\n\n"
        "**RULE 2: The 'Session Arc' (3-Act Structure)**\n"
        "   - For `indexAnalysis` and `rotationAnalysis`, analyze the day as a story:\n"
        "       * *Act I (Pre-Market/Open):* What was the intent? (e.g., 'Gap up on earnings')\n"
        "       * *Act II (RTH):* Did the market accept or reject that intent? (e.g., 'Sellers rejected the gap')\n"
        "       * *Act III (Close):* Who won? (e.g., 'Closed near lows, confirming weakness')\n\n"
        "**RULE 3: Level-Based Proof**\n"
        "   - You are FORBIDDEN from using generic terms like 'Market was volatile'.\n"
        "   - You MUST cite specific evidence from the provided 'Core Indices Structure' (e.g., 'SPY failed at $500 VWAP', 'XLK closed below ORL')."
    )

    # --- 2. Construct Main Prompt ---
    prompt = f"""
    [1. Previous Closing Context (The Anchor - 60% Weight)]
    (This is the established narrative. Assume this is TRUE unless proven otherwise by strong new evidence.)
    {json.dumps(eod_card, indent=2)}

    [2. Log of Recent Key Actions (Context)]
    (Use this to see the 5-10 day 'Arc' and prevent Recency Bias.)
    {json.dumps(rolling_log, indent=2)}

    [3. Raw Market News (The 'Why' - Narrative Source)]
    (Synthesize 'Headwinds' vs 'Tailwinds' from this raw text.)
    {news_input or "No raw market news was provided."}
    
    [4. Core Indices Structure (The 'How' - 40% Weight - EVIDENCE)]
    (CRITICAL: Look for Value Migration, Key Level Breaks (VWAP, ORL, ORH), and Trend Alignment in SPY, QQQ, Sectors, Bonds, etc.)
    {json.dumps(etf_structures, indent=2)}

    [Your Task for {analysis_date_str}]
    Populate the JSON template below based on the '60/40 Synthesis' of the above data.
    
    **Special Instructions for 'masterclass' Object:**
    * **Confidence:** Combine the Lagging Trend with Real-Time 'Story Confidence'.
    * **Screener Briefing:** Provide the specific TACTICAL setup for the *next* session (e.g. "Plan A: Long if SPY holds $500").

    [Output Format Constraint]
    Output ONLY a single, valid JSON object in this exact format.
    
    {{
        "marketNarrative": "The high-level governing narrative summary (The 60/40 Synthesis).",
        "marketBias": "Bullish / Bearish / Neutral (The Concluded State).",
        "keyEconomicEvents": {{
            "last_24h": "Synthesized summary of past events.",
            "next_24h": "Synthesized summary of upcoming events."
        }},
        "sectorRotation": {{
            "leadingSectors": ["XLK", "XLC", "..."],
            "laggingSectors": ["XLE", "XLU", "..."],
            "rotationAnalysis": "Analysis of money flow using the 3-Act structure."
        }},
        "indexAnalysis": {{
            "pattern": "Overall pattern (e.g., 'Bearish Engulfing').",
            "SPY": "Specific analysis of SPY levels (VWAP, POC, ORL).",
            "QQQ": "Specific analysis of QQQ levels."
        }},
        "interMarketAnalysis": {{
            "bonds": "Analysis of TLT (Rates).",
            "commodities": "Analysis of Oil/Gold.",
            "currencies": "Analysis of DXY/UUP.",
            "crypto": "Analysis of BTC."
        }},
        "marketInternals": {{
            "volatility": "Analysis of VIX."
        }},
        "todaysAction": "A single, loggable sentence summarizing the day's verifyable outcome.",
        "masterclass": {{
            "confidence": "Trend_Bias: ... (Story_Confidence: ...) - Reasoning: ...",
            "screener_briefing": "Setup_Bias: ...\\nJustification: ...\\nCatalyst: ...\\nPattern: ...\\n...",
            "basicContext": {{
                "priceTrend": "...",
                "recentCatalyst": "..."
            }},
            "technicalStructure": {{
                "majorSupport": "...",
                "majorResistance": "...",
                "pattern": "...",
                "volumeMomentum": "..."
            }},
            "behavioralSentiment": {{
                "buyerVsSeller": "...",
                "emotionalTone": "...",
                "newsReaction": "..."
            }},
            "marketOutlook": {{
                "planName": "Primary Market Scenario",
                "knownParticipant": "...",
                "expectedParticipant": "...",
                "trigger": "...",
                "invalidation": "..."
            }}
        }}
    }}
    """
    
    return prompt, system_prompt
