import unittest
import json
import sys
import os
from datetime import date

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We mock out call_gemini_api since it makes network requests
from unittest.mock import MagicMock, patch
import backend.engine.analysis.detail_engine as detail_engine

class TestDetailEngine(unittest.TestCase):
    
    def test_card_reconstruction(self):
        """Should correctly merge AI response into a full Battle Card."""
        ticker = "AAPL"
        prev_card = {
            "marketNote": "Old Note",
            "basicContext": {"tickerDate": "AAPL | 2024-01-01", "sector": "Tech"},
            "technicalStructure": {"keyActionLog": [{"date": "2024-01-01", "action": "Old action"}]}
        }
        
        ai_response = {
            "marketNote": "New Note",
            "confidence": "High",
            "todaysAction": "New price action summary",
            "behavioralSentiment": {"emotionalTone": "Bullish Accumulation"}
        }
        
        # Mocking call_gemini_api to return our dummy JSON
        with patch('backend.engine.analysis.detail_engine.call_gemini_api') as mock_api:
            mock_api.return_value = json.dumps(ai_response)
            
            result_json = detail_engine.update_company_card(
                ticker=ticker,
                previous_card_json=json.dumps(prev_card),
                previous_card_date="2024-01-01",
                historical_notes="Major support at 180",
                new_eod_summary="Strong close",
                new_eod_date=date(2024, 2, 14),
                model_name="gemini-2.0-flash",
                key_manager=MagicMock(),
                pre_fetched_context="{}",
                market_context_summary="Bullish news"
            )
            
            result = json.loads(result_json)
            
            # Verify merging
            self.assertEqual(result['marketNote'], "New Note")
            self.assertEqual(result['basicContext']['sector'], "Tech") # Preserved
            self.assertEqual(result['confidence'], "High")
            
            # Verify log appending
            log = result['technicalStructure']['keyActionLog']
            self.assertEqual(len(log), 2)
            self.assertEqual(log[-1]['action'], "New price action summary")
            self.assertEqual(log[-1]['date'], "2024-02-14")

if __name__ == '__main__':
    unittest.main()
