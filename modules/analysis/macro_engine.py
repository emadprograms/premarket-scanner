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
    logger: AppLogger
) -> tuple[str, str]:
    """
    Constructs the 'Masterclass' System Prompt and Main Prompt for the Economy Card.
    Returns: (prompt, system_prompt)
    """
    
    # --- 1. Construct System Prompt (The Masterclass Philosophy) ---
    system_prompt = (
        "You are an expert Global Macro Strategist. Your *only* job is to apply the specific 4-Participant Trading Model to the BROAD MARKET (SPY/QQQ). "
        "Your logic must *strictly* follow this model. You will be given a 'Masterclass' in the prompt that defines the philosophy. "
        "Your job has **four** distinct analytical tasks for the MARKET as a whole: "
        "1. **Analyze `behavioralSentiment` (The 'Micro'):** You MUST provide a full 'Proof of Reasoning' for the `emotionalTone` of the indices. "
        "2. **Analyze `technicalStructure` (The 'Macro'):** Use *repeated* participant behavior to define the *key market zones*. "
        "3. **Calculate `confidence` (The 'Story'):** You MUST combine the lagging 'Trend_Bias' with the 'Story_Confidence' (H/M/L). "
        "4. **Calculate `screener_briefing` (The 'Tactic'):** You MUST synthesize your analysis to calculate a *new, actionable* 'Setup_Bias' for the general market. "
        "Do not use any of your own default logic. Your sole purpose is to be a processor for the user's provided framework."
    )

    # --- 2. Construct Main Prompt ---
    prompt = f"""
    [Raw Market Context for Today]
    (This contains RAW, unstructured news headlines and snippets. Synthesize the "Headwind" or "Tailwind" from this data.)
    {news_input or "No raw market news was provided."}

    [Previous Closing Context (EOD Card)]
    (This is the established structure from the previous session.)
    {json.dumps(eod_card, indent=2)}
    
    [Core Indices Structure (Pre-Market)]
    (Analysis of SPY, QQQ, IWM, VIX etc. - Look for Migration & Rejections in these pre-market blocks.)
    {json.dumps(etf_structures, indent=2)}

    [Your Task for {analysis_date_str}]
    Your task is to populate the JSON template below. You MUST use the following trading model to generate your analysis.

    --- START MASTERCLASS: THE 4-PARTICIPANT MODEL ---
    (See 'Company Card' prompt for full 4-Participant definitions. They apply identically here to the Index participants.)
    * **Committed Buyers/Sellers:** Institutional flows, defining broad support/resistance.
    * **Desperate Buyers/Sellers:** FOMO/Panic flows, driving volatility and 'Unstable' moves.
    * **Patterns:** Accumulation, Capitulation, Stable Uptrend, Washout & Reclaim, Chop.
    * **Story Confidence:** High, Medium, Low based on decisive closes vs. failures.

    --- END MASTERCLASS ---

    **YOUR EXECUTION TASK (Filling the JSON):**

    **1. Calculate `marketNarrative`:** 
        * Write a clear, high-level summary of the "Governing Narrative" for the entire market based on the News + Price Action.
    
    **2. Calculate `marketBias`:**
        * "Bullish", "Bearish", or "Neutral". This is the high-level label.

    **3. Populate `masterclass` Object (The Deep Dive):**
        * **`confidence`:** "Trend_Bias: [Bias] (Story_Confidence: [H/M/L]) - Reasoning: [Proof]"
        * **`basicContext.priceTrend`:** Cumulative trend summary.
        * **`technicalStructure`:** Define `majorSupport` and `majorResistance` for SPY/QQQ based on the provided index structure.
        * **`technicalStructure.pattern`:** The structural narrative (e.g. "Consolidating above $SPY 500").
        * **`behavioralSentiment.emotionalTone`:** The 3-Act Arc (Pre-Market -> RTH -> Post-Market) justification.
        * **`behavioralSentiment.newsReaction`:** Did the market validate or ignore the bad/good news? (Surprise factor).
        * **`screener_briefing`:** The Data Packet. Setup_Bias, Justification, Catalyst, Pattern, Plans, Levels.

    [Output Format Constraint]
    Output ONLY a single, valid JSON object in this exact format.
    
    {{
        "marketNarrative": "Your high-level governing narrative summary (Masterclass Synthesis).",
        "marketBias": "Bullish/Bearish/Neutral",
        "keyEconomicEvents": {{
             "last_24h": "Summary of key data/earnings from yesterday/overnight.",
             "next_24h": "Summary of upcoming key data/earnings."
        }},
        "indexAnalysis": {{
            "pattern": "Your Masterclass Structural Narrative (e.g. 'Consolidating above $SPY 500').",
            "SPY": "Specific analysis of SPY structure.",
            "QQQ": "Specific analysis of QQQ structure.",
            "IWM": "Specific analysis of IWM structure.",
            "VIX": "Specific analysis of VIX structure."
        }},
        "sectorRotation": {{
            "leadingSectors": ["Sector1", "Sector2"],
            "laggingSectors": ["Sector1", "Sector2"],
            "rotationAnalysis": "Brief analysis of flows (Defensive vs Cyclical)."
        }},
        "interMarketAnalysis": {{
             "Dollar_DXY": "Trend/Impact analysis.",
             "Yields_10Y": "Trend/Impact analysis.",
             "Gold_GLD": "Trend/Impact analysis.",
             "Crypto_BTC": "Trend/Impact analysis."
        }},
        "keyActionLog": [
            {{ "date": "{analysis_date_str}", "action": "Summary of today's key market action." }}
        ],
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
