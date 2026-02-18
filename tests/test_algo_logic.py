
import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add parent dir to path so we can import backend.engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.engine.processing import detect_impact_levels

class TestImpactAlgo(unittest.TestCase):
    
    def test_empty_dataframe(self):
        """Edge Case: Empty DataFrame should return empty list."""
        df = pd.DataFrame()
        result = detect_impact_levels(df)
        self.assertEqual(result, [], "Empty DF should return no levels")

    def test_flat_line_price(self):
        """Edge Case: Zero volatility should return no levels."""
        df = pd.DataFrame({
            "Open": [100]*100,
            "High": [100]*100,
            "Low": [100]*100,
            "Close": [100]*100
        })
        result = detect_impact_levels(df)
        self.assertEqual(result, [], "Flat line should have no pivots")

    def test_single_sharp_rejection(self):
        """Scenario: A perfect ^ shape rejection."""
        # Price goes 100 -> 105 -> 100
        prices = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100]
        df = pd.DataFrame({
            "Open": prices,
            "High": prices,
            "Low": prices,
            "Close": prices
        })
        # Need to ensure index is handled if processing.py expects it? 
        # The current implementation uses RangeIndex by default in tests.
        
        result = detect_impact_levels(df)
        
        # We expect at least one Resistance level at 105
        resistances = [x for x in result if x['type'] == 'RESISTANCE']
        self.assertTrue(len(resistances) > 0, "Should detect the peak at 105")
        if resistances:
            self.assertAlmostEqual(resistances[0]['level'], 105, delta=0.1)

    def test_nan_handling(self):
        """Edge Case: Data contains NaNs."""
        df = pd.DataFrame({
            "Open": [100, 101, np.nan, 102],
            "High": [100, 101, np.nan, 102],
            "Low": [100, 101, np.nan, 102],
            "Close": [100, 101, np.nan, 102]
        })
        # This checks if it crashes or handles it. 
        try:
            detect_impact_levels(df)
        except Exception as e:
            self.fail(f"Algo crashed on NaNs: {e}")

if __name__ == '__main__':
    unittest.main()
