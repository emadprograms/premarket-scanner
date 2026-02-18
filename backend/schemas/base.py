from pydantic import BaseModel
from typing import List, Dict, Optional, Any

class MacroRequest(BaseModel):
    model_name: str
    benchmark_date: str
    simulation_cutoff: str
    news_text: str = ""
    mode: str = "Live"
    db_fallback: bool = False
    force_execution: bool = False

class ScannerRequest(BaseModel):
    benchmark_date: str
    simulation_cutoff: str
    mode: str = "Live"
    threshold: float = 2.5
    db_fallback: bool = False
    refresh_tickers: List[str] = []   # Tickers to fetch live; others use DB fallback
    plan_only: bool = False           # If True, proximity checks only against Plan A/B levels

class RankingRequest(BaseModel):
    selected_tickers: List[str]
    confluence_mode: str = "Flexible"
    use_full_context: bool = False    # If False, use only screener_briefing (token-saving)
    prioritize_rr: bool = False
    prioritize_prox: bool = False
    model_name: str
    benchmark_date: str
    simulation_cutoff: str
    macro_context: Dict               # The economy card JSON
    market_cards: Dict[str, Dict]     # Ticker -> Analysis Card map

class DeepDiveRequest(BaseModel):
    tickers: List[str]
    benchmark_date: str
    model_name: str
    macro_summary: str

class GenericResponse(BaseModel):
    status: str
    message: str
    data: Optional[Any] = None
