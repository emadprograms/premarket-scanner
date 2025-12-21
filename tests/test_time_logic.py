
import unittest
from datetime import datetime, timedelta

class TestTimeLogic(unittest.TestCase):
    
    def test_simulation_cutoff(self):
        """Verify logic that filters list of items based on timestamp string."""
        
        cutoff_time_str = "14:00" # 09:00 ET
        
        # Simulated Data Packet (Mocking 'value_migration_log')
        data = [
            {"time_window": "13:30 - 14:00", "data": "Period 1"}, # Should Keep (Starts before)
            {"time_window": "14:00 - 14:30", "data": "Period 2"}, # Should Drop (Starts at cutoff)
            {"time_window": "14:30 - 15:00", "data": "Period 3"}, # Should Drop
        ]
        
        filtered = []
        for block in data:
            start_time = block['time_window'].split(' - ')[0].strip()
            if start_time < cutoff_time_str:
                filtered.append(block)
                
        self.assertEqual(len(filtered), 1, "Only 13:30 block should remain")
        self.assertEqual(filtered[0]['data'], "Period 1")

    def test_cutoff_boundary_inclusion(self):
        """Edge Case: If cutoff is exactly 14:30, what happens to 14:30 block?"""
        cutoff_time_str = "14:30"
        
        data = [
            {"time_window": "14:00 - 14:30"}, 
            {"time_window": "14:30 - 15:00"}
        ]
        
        filtered = []
        for block in data:
            start_time = block['time_window'].split(' - ')[0].strip()
            # Logic used in app: if start_time < cutoff
            if start_time < cutoff_time_str:
                filtered.append(block)
                
        # 14:00 is < 14:30 (Keep)
        # 14:30 is NOT < 14:30 (Drop) - This is correct for "Simulating AS OF 14:30"
        # We don't see the future 14:30-15:00 candle yet.
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['time_window'], "14:00 - 14:30")

if __name__ == '__main__':
    unittest.main()
