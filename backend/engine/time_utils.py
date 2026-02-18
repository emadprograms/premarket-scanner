import pytz
from datetime import datetime, time as dt_time
from typing import Optional, Union

US_EASTERN = pytz.timezone('US/Eastern')
UTC = pytz.utc
MARKET_OPEN_TIME = dt_time(9, 30)
MARKET_CLOSE_TIME = dt_time(16, 0)

def now_et() -> datetime:
    """Returns the current time in US/Eastern."""
    return datetime.now(US_EASTERN)

def now_utc() -> datetime:
    """Returns the current time in UTC."""
    return datetime.now(UTC)

def to_et(dt: datetime) -> datetime:
    """Converts a datetime object to US/Eastern."""
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(US_EASTERN)

def to_utc(dt: datetime) -> datetime:
    """Converts a datetime object to UTC."""
    if dt.tzinfo is None:
        dt = US_EASTERN.localize(dt)
    return dt.astimezone(UTC)

def format_time_et(dt: datetime) -> str:
    """Formats a datetime as HH:MM:SS ET."""
    return to_et(dt).strftime('%H:%M:%S') + " ET"

def is_market_open(dt: Optional[datetime] = None) -> bool:
    """Checks if the US market is currently open (Regular Trading Hours)."""
    if dt is None:
        dt = now_et()
    else:
        dt = to_et(dt)
    
    # 0 is Monday, 4 is Friday
    if dt.weekday() > 4:
        return False
        
    current_time = dt.time()
    return MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME

def get_staleness_score(dt: datetime) -> float:
    """Returns the number of minutes since the provided datetime."""
    dt_utc = to_utc(dt)
    current_utc = now_utc()
    return (current_utc - dt_utc).total_seconds() / 60.0
