import unittest
import json
import sys
import os

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.engine.analysis.macro_engine import summarize_rolling_log, generate_economy_card_prompt
from backend.engine.utils import AppLogger

class TestAnalysisEngines(unittest.TestCase):
    
    def setUp(self):
        self.logger = AppLogger(None)

    def test_summarize_rolling_log_short(self):
        """Should return the full log if it's short."""
        log = [{"date": "2024-01-01", "action": "Test action"}]
        result = summarize_rolling_log(log, self.logger)
        self.assertIn("Test action", result)
        self.assertIn("2024-01-01", result)

    def test_summarize_rolling_log_long(self):
        """Should summarize a long log into the Arc structure."""
        log = [{"date": f"2024-01-{i:02d}", "action": f"Action {i}"} for i in range(1, 21)]
        result = summarize_rolling_log(log, self.logger)
        
        self.assertIn("### HISTORICAL MACRO ARC", result)
        self.assertIn("Regime Origins:", result)
        self.assertIn("Mid-Cycle Shift:", result)
        self.assertIn("Recent Regime", result)
        
        # Check first and last entries are preserved
        self.assertIn("Action 1", result)
        self.assertIn("Action 20", result)

    def test_generate_economy_card_prompt(self):
        """Should return a prompt and system prompt containing key sections."""
        eod_card = {"marketBias": "Bullish"}
        etf_structures = [{"ticker": "SPY", "latest_price": 500}]
        news = "Interest rates stay high."
        date_str = "2024-02-14"
        
        prompt, system_prompt = generate_economy_card_prompt(
            eod_card, etf_structures, news, date_str, self.logger
        )
        
        self.assertIn("Senior Market Analyst", system_prompt)
        self.assertIn("Executive Briefing", system_prompt)
        self.assertIn("Narrative Clarity", system_prompt)
        self.assertIn("SPY", prompt)

if __name__ == '__main__':
    unittest.main()
