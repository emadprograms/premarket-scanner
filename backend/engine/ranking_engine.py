import logging
import math
from typing import Dict, List, Optional, Tuple
from backend.engine.processing import calculate_atr

log = logging.getLogger(__name__)

class ProximityRankingEngine:
    """
    Ranks stocks based on the proximity of live price to Plan A/B levels.
    Uses ATR normalization to handle different price ranges.
    """
    
    def calculate_proximity_score(
        self, 
        current_price: float, 
        plan_a: Optional[float], 
        plan_b: Optional[float], 
        atr: float
    ) -> Tuple[float, Optional[str], Optional[float]]:
        """
        Calculates the normalized proximity score.
        Returns: (score, nearest_level_type, nearest_level_value)
        Score: Lower is better (0.0 means at the level).
        """
        if not current_price or (not plan_a and not plan_b):
            return float('inf'), None, None
            
        # 1. Determine Distance to Levels
        dist_a = abs(current_price - plan_a) if plan_a else float('inf')
        dist_b = abs(current_price - plan_b) if plan_b else float('inf')
        
        # 2. Find the Nearest Level
        if dist_a <= dist_b:
            nearest_dist = dist_a
            level_type = "PLAN A"
            level_val = plan_a
        else:
            nearest_dist = dist_b
            level_type = "PLAN B"
            level_val = plan_b
            
        # 3. ATR Normalization (Volatility-Adjusted Proximity)
        # We divide the raw distance by ATR.
        # This tells us how many "typical moves" away the price is.
        # $100 stock moving $1 with ATR $1.0 = 1.0 score.
        # $500 stock moving $5 with ATR $5.0 = 1.0 score.
        # These are now ranked as equally tradable!
        
        if atr > 0:
            score = nearest_dist / atr
        else:
            # Fallback if ATR is missing (e.g., first few bars of session)
            # Use raw percentage for fallback
            score = (nearest_dist / current_price) * 100
            
        return score, level_type, level_val

    def rank_cards(self, cards: List[Dict]) -> List[Dict]:
        """
        Takes a list of card objects with current price, ATR, and Plan levels.
        Sorts them by proximity score.
        
        Input Card Expectation:
        {
            "ticker": "AAPL",
            "current_price": 180.50,
            "atr": 2.50,
            "plan_a": 181.0,
            "plan_b": 178.0,
            ...
        }
        """
        for card in cards:
            score, l_type, l_val = self.calculate_proximity_score(
                card.get("current_price"),
                card.get("plan_a"),
                card.get("plan_b"),
                card.get("atr", 0)
            )
            card["proximity_score"] = score
            card["nearest_level_type"] = l_type
            card["nearest_level_value"] = l_val
            
        # Sort by proximity score (ascending, lower is better)
        # Tie-breaker: If scores are equal, prioritize PLAN A
        def sort_key(c):
            # level_type priority: PLAN A (0) < PLAN B (1)
            type_prio = 0 if c["nearest_level_type"] == "PLAN A" else 1
            return (c["proximity_score"], type_prio)
            
        return sorted(cards, key=sort_key)

# Global Instance
ranking_engine = ProximityRankingEngine()
