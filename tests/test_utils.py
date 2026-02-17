import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from modules.utils import AppLogger

class TestAppLogger(unittest.TestCase):
    def test_log(self):
        logger = AppLogger(None)
        logger.log("test message")
        self.assertEqual(len(logger.log_messages), 1)
        self.assertIn("test message", logger.log_messages[0])

if __name__ == '__main__':
    unittest.main()
