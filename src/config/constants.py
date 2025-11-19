# constants.py
from pytz import timezone as pytz_timezone

US_EASTERN = pytz_timezone('US/Eastern')
PREMARKET_START_HOUR = 4
PREMARKET_END_HOUR = 9
PREMARKET_END_MINUTE = 30

MODEL_NAME = "gemini-2.5-flash-preview-09-2025"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
CAPITAL_API_URL_BASE = "https://api-capital.backend-capital.com/api/v1"

CORE_INTERMARKET_EPICS = [
    "SPY_SPX", "QQQ_NDX", "IWM_RUT", "DIA_DJI",
    "XLF", "XLE", "XLK", "XLI", "XLP", "XLU", "XLV",
    "TLT_US_20Y", "UUP_DXY", "Gold_GLD", "USO_WTI",
]

LOOP_DELAY = 0.33
