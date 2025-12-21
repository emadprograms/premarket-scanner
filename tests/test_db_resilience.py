
import unittest
import streamlit as st
import sys
import os
import json

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from libsql_client import create_client_sync

class TestDBResilience(unittest.TestCase):
    
    def setUp(self):
        # Setup DB Connection from secrets
        try:
            secrets = st.secrets["turso"]
            url = secrets["db_url"].replace("libsql://", "https://")
            token = secrets["auth_token"]
            self.client = create_client_sync(url=url, auth_token=token)
        except Exception as e:
            self.skipTest(f"Skipping DB tests: Could not connect. {e}")

    def tearDown(self):
        if hasattr(self, 'client'):
            self.client.close()

    def test_fetch_valid_ticker(self):
        """Test fetching a known good ticker (MSFT)."""
        # Note: Validated table is company_cards
        query = "SELECT company_card_json FROM company_cards WHERE ticker = ? ORDER BY date DESC LIMIT 1"
        rows = self.client.execute(query, ["MSFT"]).rows
        
        self.assertTrue(len(rows) > 0, "Should find data for MSFT")
        
        # Verify JSON parsing
        try:
            data = json.loads(rows[0][0])
            self.assertIn('basicContext', data, "JSON should have basicContext")
        except json.JSONDecodeError:
            self.fail("Failed to parse company_card_json for MSFT")

    def test_fetch_invalid_ticker(self):
        """Test fetching a non-existent ticker (ZZZZ)."""
        query = "SELECT company_card_json FROM company_cards WHERE ticker = ? ORDER BY date DESC LIMIT 1"
        rows = self.client.execute(query, ["ZZZZ"]).rows
        
        self.assertEqual(len(rows), 0, "Should return 0 rows for invalid ticker")

    def test_sql_injection_resilience(self):
        """Test if query parameter binding prevents injection."""
        # Attempt to inject 
        malicious = "MSFT' OR '1'='1"
        query = "SELECT company_card_json FROM company_cards WHERE ticker = ? ORDER BY date DESC LIMIT 1"
        rows = self.client.execute(query, [malicious]).rows
        
        # Should NOT return all rows, likely 0
        self.assertEqual(len(rows), 0, "SQL Injection should be neutralized by binding")

if __name__ == '__main__':
    unittest.main()
