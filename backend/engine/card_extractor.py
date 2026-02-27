"""
card_extractor.py — Robust extraction of screener briefing data from company card JSON.

Handles both formats:
  1. JSON object: {"Plan_A_Level": "255.84", "Setup_Bias": "Bullish", ...}
  2. Raw string:  "Plan_A_Level: $255.84\nSetup_Bias: Bullish\n..."

Extracts:
  - plan_a_level (float)
  - plan_b_level (float)
  - plan_a_text  (str)  — e.g. "Long Support Defense"
  - plan_b_text  (str)  — e.g. "Short the Resistance Rejection"
  - plan_a_nature (str) — SUPPORT | RESISTANCE | UNKNOWN (derived from plan text)
  - plan_b_nature (str) — SUPPORT | RESISTANCE | UNKNOWN (derived from plan text)
  - setup_bias   (str)  — Bullish | Bearish | Neutral
"""

import json
import re
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

# ── Keywords for classifying plan text as SUPPORT or RESISTANCE ──
_SUPPORT_KEYWORDS = [
    "support", "long", "buy", "base", "floor", "defense", "reclaim",
    "bounce", "reversal", "hold", "recapture", "rebound", "mean reversion from support"
]
_RESISTANCE_KEYWORDS = [
    "resistance", "short", "sell", "rejection", "fail", "ceiling",
    "breakdown", "markdown", "continuation", "distribution", "look above and fail"
]


def classify_plan_nature(plan_text: str) -> str:
    """
    Determines if a plan is SUPPORT or RESISTANCE based on the plan description text.
    e.g. "Long Support Defense" → SUPPORT
         "Short the Resistance Rejection" → RESISTANCE
    """
    if not plan_text:
        return "UNKNOWN"

    text_lower = plan_text.lower().strip()

    support_score = 0
    resistance_score = 0

    for kw in _SUPPORT_KEYWORDS:
        if kw in text_lower:
            support_score += 1

    for kw in _RESISTANCE_KEYWORDS:
        if kw in text_lower:
            resistance_score += 1

    if support_score > resistance_score:
        return "SUPPORT"
    elif resistance_score > support_score:
        return "RESISTANCE"
    else:
        # Tie-break: Check if it starts with "Long" or "Short"
        if text_lower.startswith("long"):
            return "SUPPORT"
        elif text_lower.startswith("short"):
            return "RESISTANCE"
        return "UNKNOWN"


def _extract_price(value: Any) -> Optional[float]:
    """Extract a float price from various formats: '$255.84', '255.84', 255.84, etc."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    match = re.search(r'[\d.]+', s)
    return float(match.group()) if match else None


def extract_screener_briefing(card_json_str: str) -> Dict[str, Any]:
    """
    Main entry point. Given a raw card JSON string, extract all screener briefing fields.
    
    Returns dict with:
      - plan_a_level: float | None
      - plan_b_level: float | None
      - plan_a_text:  str
      - plan_b_text:  str
      - plan_a_nature: 'SUPPORT' | 'RESISTANCE' | 'UNKNOWN'
      - plan_b_nature: 'SUPPORT' | 'RESISTANCE' | 'UNKNOWN'
      - setup_bias:   str ('Bullish', 'Bearish', 'Neutral')
    """
    result = {
        "plan_a_level": None,
        "plan_b_level": None,
        "plan_a_text": "",
        "plan_b_text": "",
        "plan_a_nature": "UNKNOWN",
        "plan_b_nature": "UNKNOWN",
        "setup_bias": "Neutral"
    }

    if not card_json_str:
        return result

    try:
        card_data = json.loads(card_json_str)
    except (json.JSONDecodeError, TypeError):
        log.warning("card_extractor: Failed to parse card JSON, treating as empty.")
        return result

    briefing = card_data.get("screener_briefing")
    if not briefing:
        return result

    # Route to the correct parser
    if isinstance(briefing, dict):
        return _extract_from_dict(briefing, result)
    elif isinstance(briefing, str):
        # Try JSON parse first (some strings are JSON-encoded dicts)
        try:
            parsed = json.loads(briefing)
            if isinstance(parsed, dict):
                return _extract_from_dict(parsed, result)
        except (json.JSONDecodeError, TypeError):
            pass
        # Fall through to regex string extraction
        return _extract_from_string(briefing, result)
    else:
        return result


def _extract_from_dict(obj: dict, result: dict) -> dict:
    """Extract fields from a dict-format screener briefing."""
    result["plan_a_level"] = _extract_price(obj.get("Plan_A_Level"))
    result["plan_b_level"] = _extract_price(obj.get("Plan_B_Level"))
    result["plan_a_text"] = str(obj.get("Plan_A", "")).strip()
    result["plan_b_text"] = str(obj.get("Plan_B", "")).strip()
    result["setup_bias"] = str(obj.get("Setup_Bias", "Neutral")).strip()

    result["plan_a_nature"] = classify_plan_nature(result["plan_a_text"])
    result["plan_b_nature"] = classify_plan_nature(result["plan_b_text"])
    return result


def _extract_from_string(text: str, result: dict) -> dict:
    """Extract fields from a raw string-format screener briefing using regex."""

    # Plan A Level: $255.84 or Plan_A_Level: 255.84
    m = re.search(r'Plan_A_Level:\s*\$?([\d.]+)', text)
    if m:
        result["plan_a_level"] = float(m.group(1))

    # Plan B Level: $269.13 or Plan_B_Level: 269.13
    m = re.search(r'Plan_B_Level:\s*\$?([\d.]+)', text)
    if m:
        result["plan_b_level"] = float(m.group(1))

    # Plan A text: everything between "Plan_A: " and the next line
    m = re.search(r'Plan_A:\s*(.+?)(?:\n|$)', text)
    if m:
        result["plan_a_text"] = m.group(1).strip()

    # Plan B text: everything between "Plan_B: " and the next line
    m = re.search(r'Plan_B:\s*(.+?)(?:\n|$)', text)
    if m:
        result["plan_b_text"] = m.group(1).strip()

    # Setup Bias
    m = re.search(r'Setup_Bias:\s*(\w+)', text)
    if m:
        result["setup_bias"] = m.group(1).strip()

    # Classify natures from plan text
    result["plan_a_nature"] = classify_plan_nature(result["plan_a_text"])
    result["plan_b_nature"] = classify_plan_nature(result["plan_b_text"])

    return result
