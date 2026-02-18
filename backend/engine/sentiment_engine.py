import json
import re
from typing import List, Dict, Tuple
from backend.engine.gemini import call_gemini_with_rotation
from backend.engine.utils import AppLogger
from backend.engine.key_manager import KeyManager

def analyze_headline_sentiment(headlines: str, model_name: str, key_manager: KeyManager, logger: AppLogger) -> Dict:
    """
    Rapidly analyzes a batch of headlines for sentiment and sector impact.
    Returns a structured dictionary of sentiment scores.
    """
    system_prompt = (
        "You are an Institutional News Analyst. Your job is to extract market sentiment from headlines.\n"
        "Provide a score from -1.0 (Extremely Bearish) to 1.0 (Extremely Bullish) for each significant sector and the overall market.\n"
        "Output ONLY valid JSON."
    )
    
    prompt = f"""
    Analyze the following headlines:
    {headlines}
    
    Output Format:
    {{
        "overall_sentiment": 0.0,
        "sectors": {{
            "Tech": 0.0,
            "Energy": 0.0,
            "Finance": 0.0,
            ...
        }},
        "reasoning": "Quick 1-sentence summary of themes."
    }}
    """
    
    resp, error = call_gemini_with_rotation(prompt, system_prompt, logger, model_name, key_manager)
    if resp:
        try:
            # Extract JSON from potential markdown blocks
            clean = re.search(r"(\{.*\})", resp, re.DOTALL).group(1)
            return json.loads(clean)
        except Exception as e:
            logger.error(f"Sentiment JSON Parse Error: {e}")
            return {"overall_sentiment": 0.0, "sectors": {}, "reasoning": "Error parsing sentiment response."}
    
    return {"overall_sentiment": 0.0, "sectors": {}, "reasoning": "Sentiment analysis failed."}
