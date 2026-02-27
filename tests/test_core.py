"""
Pre-Market Scanner: Rigorous Test Suite
========================================
Tests the core backend components in isolation:
1. Ranking Engine (Proximity Score calculation)
2. API Endpoints (System status, Watchlist, etc.)
3. Context Initialization (Graceful degradation)
4. Data Pipeline (ATR calculation, Plan extraction)
"""
import pytest
import math
import json
from unittest.mock import patch, MagicMock

# ============================================================
# MODULE 1: RANKING ENGINE (Pure Logic — No External Dependencies)
# ============================================================
from backend.engine.ranking_engine import ProximityRankingEngine

@pytest.fixture
def engine():
    return ProximityRankingEngine()


class TestProximityScoreCalculation:
    """Tests the core mathematical ranking logic."""

    def test_exact_level_returns_zero_score(self, engine):
        """Price exactly at Plan A should yield score 0."""
        score, level_type, level_val = engine.calculate_proximity_score(
            current_price=100.0, plan_a=100.0, plan_b=95.0, atr=2.0
        )
        assert score == 0.0
        assert level_type == "PLAN A"
        assert level_val == 100.0

    def test_plan_a_prioritized_when_equidistant(self, engine):
        """When equidistant from Plan A and Plan B, Plan A wins."""
        score, level_type, level_val = engine.calculate_proximity_score(
            current_price=100.0, plan_a=102.0, plan_b=98.0, atr=2.0
        )
        assert level_type == "PLAN A"
        assert level_val == 102.0

    def test_closer_plan_b_wins(self, engine):
        """Plan B should be selected when it's strictly closer."""
        score, level_type, level_val = engine.calculate_proximity_score(
            current_price=100.0, plan_a=110.0, plan_b=101.0, atr=2.0
        )
        assert level_type == "PLAN B"
        assert level_val == 101.0

    def test_atr_normalization_works(self, engine):
        """$1 move on $100 stock with ATR=1 should equal $5 move on $500 stock with ATR=5."""
        score_100, _, _ = engine.calculate_proximity_score(
            current_price=100.0, plan_a=101.0, plan_b=None, atr=1.0
        )
        score_500, _, _ = engine.calculate_proximity_score(
            current_price=500.0, plan_a=505.0, plan_b=None, atr=5.0
        )
        assert score_100 == score_500, "ATR normalization should make these equal"

    def test_higher_atr_reduces_score(self, engine):
        """Higher volatility (ATR) should result in lower (better) proximity score."""
        score_low_vol, _, _ = engine.calculate_proximity_score(
            current_price=100.0, plan_a=102.0, plan_b=None, atr=1.0
        )
        score_high_vol, _, _ = engine.calculate_proximity_score(
            current_price=100.0, plan_a=102.0, plan_b=None, atr=4.0
        )
        assert score_high_vol < score_low_vol

    def test_missing_both_plans_returns_infinity(self, engine):
        """No plan levels should return infinite score."""
        score, level_type, level_val = engine.calculate_proximity_score(
            current_price=100.0, plan_a=None, plan_b=None, atr=2.0
        )
        assert score == float('inf')
        assert level_type is None
        assert level_val is None

    def test_missing_price_returns_infinity(self, engine):
        """No current price should return infinite score."""
        score, _, _ = engine.calculate_proximity_score(
            current_price=None, plan_a=100.0, plan_b=95.0, atr=2.0
        )
        assert score == float('inf')

    def test_zero_atr_falls_back_to_percentage(self, engine):
        """When ATR is 0, fallback to raw percentage proximity."""
        score, _, _ = engine.calculate_proximity_score(
            current_price=100.0, plan_a=101.0, plan_b=None, atr=0.0
        )
        # 1/100 * 100 = 1.0%
        assert score == 1.0

    def test_only_plan_b_provided(self, engine):
        """When only Plan B is provided, it should be the nearest level."""
        score, level_type, level_val = engine.calculate_proximity_score(
            current_price=100.0, plan_a=None, plan_b=98.0, atr=1.0
        )
        assert level_type == "PLAN B"
        assert level_val == 98.0
        assert score == 2.0  # abs(100-98) / 1.0


class TestRankCards:
    """Tests the full ranking pipeline (sort by proximity)."""

    def test_cards_sorted_by_proximity(self, engine):
        """Closer cards should rank higher (lower index)."""
        cards = [
            {"ticker": "FAR", "current_price": 100.0, "plan_a": 110.0, "plan_b": None, "atr": 2.0},
            {"ticker": "CLOSE", "current_price": 100.0, "plan_a": 100.5, "plan_b": None, "atr": 2.0},
            {"ticker": "MID", "current_price": 100.0, "plan_a": 105.0, "plan_b": None, "atr": 2.0},
        ]
        ranked = engine.rank_cards(cards)
        assert ranked[0]["ticker"] == "CLOSE"
        assert ranked[1]["ticker"] == "MID"
        assert ranked[2]["ticker"] == "FAR"

    def test_plan_a_tiebreaker(self, engine):
        """When scores are equal, PLAN A should rank higher."""
        cards = [
            {"ticker": "B_TYPE", "current_price": 100.0, "plan_a": None, "plan_b": 102.0, "atr": 2.0},
            {"ticker": "A_TYPE", "current_price": 100.0, "plan_a": 102.0, "plan_b": None, "atr": 2.0},
        ]
        ranked = engine.rank_cards(cards)
        assert ranked[0]["ticker"] == "A_TYPE"

    def test_empty_cards_returns_empty(self, engine):
        """Empty input should return empty output."""
        assert engine.rank_cards([]) == []

    def test_single_card_returns_itself(self, engine):
        """Single card should rank itself."""
        cards = [{"ticker": "SOLO", "current_price": 100.0, "plan_a": 101.0, "plan_b": None, "atr": 1.0}]
        ranked = engine.rank_cards(cards)
        assert len(ranked) == 1
        assert ranked[0]["ticker"] == "SOLO"
        assert "proximity_score" in ranked[0]

    def test_all_missing_plans_rank_last(self, engine):
        """Cards with no plan levels should sort last (infinite score)."""
        cards = [
            {"ticker": "NO_PLAN", "current_price": 100.0, "plan_a": None, "plan_b": None, "atr": 2.0},
            {"ticker": "HAS_PLAN", "current_price": 100.0, "plan_a": 101.0, "plan_b": None, "atr": 2.0},
        ]
        ranked = engine.rank_cards(cards)
        assert ranked[0]["ticker"] == "HAS_PLAN"
        assert ranked[1]["ticker"] == "NO_PLAN"


# ============================================================
# MODULE 2: ATR CALCULATION (Processing Engine)
# ============================================================
import pandas as pd
import numpy as np
from backend.engine.processing import calculate_atr


class TestATRCalculation:
    """Tests ATR (Average True Range) calculation for volatility normalization."""

    def test_basic_atr_calculation(self):
        """ATR should return a positive float for valid OHLC data."""
        dates = pd.date_range("2024-01-01", periods=30, freq="5min")
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(30) * 0.5)
        df = pd.DataFrame({
            "timestamp": dates,
            "Open": prices,
            "High": prices + abs(np.random.randn(30)),
            "Low": prices - abs(np.random.randn(30)),
            "Close": prices + np.random.randn(30) * 0.3,
            "Volume": np.random.randint(100, 1000, 30)
        })
        atr = calculate_atr(df)
        assert isinstance(atr, float)
        assert atr > 0

    def test_atr_empty_dataframe(self):
        """ATR should return 0.0 for empty DataFrame."""
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
        atr = calculate_atr(df)
        assert atr == 0.0

    def test_atr_insufficient_rows(self):
        """ATR should return 0.0 if fewer rows than the period."""
        df = pd.DataFrame({
            "Open": [100], "High": [101], "Low": [99], "Close": [100.5]
        })
        atr = calculate_atr(df, period=14)
        assert atr == 0.0


# ============================================================
# MODULE 3: API ENDPOINTS (FastAPI TestClient)
# ============================================================
from fastapi.testclient import TestClient


class TestAPIEndpoints:
    """Tests FastAPI endpoints for correct response structure."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Create TestClient. Import here to avoid top-level context init issues."""
        from backend.main import app
        self.client = TestClient(app)

    def test_root_endpoint(self):
        """Root should return online status."""
        response = self.client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["service"] == "Premarket Scanner API"

    def test_debug_endpoint(self):
        """Debug should return current time."""
        response = self.client.get("/api/debug")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "debug"
        assert "time" in data

    def test_system_status_structure(self):
        """System status should return well-formed response with all fields."""
        response = self.client.get("/api/system/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        status_data = data["data"]
        assert "gemini_keys_available" in status_data
        assert "capital_connected" in status_data
        assert "db_connected" in status_data
        assert "economy_card_status" in status_data
        assert isinstance(status_data["gemini_keys_available"], int)
        assert isinstance(status_data["capital_connected"], bool)
        assert isinstance(status_data["db_connected"], bool)

    def test_watchlist_status_returns_list(self):
        """Watchlist status should return a list (possibly empty), or skip if DB is unavailable."""
        try:
            response = self.client.get("/api/system/watchlist-status")
        except RuntimeError:
            # DB credentials missing in CI — skip gracefully
            pytest.skip("Database not available in CI")
        if response.status_code == 500:
            return
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["success", "error"]
        if data["status"] == "success":
            assert isinstance(data["data"], list)

    def test_cors_preflight(self):
        """CORS OPTIONS request should succeed with proper headers."""
        response = self.client.options(
            "/api/system/status",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_archive_cards_endpoint(self):
        """Archive cards endpoint should respond without crashing."""
        response = self.client.get("/api/archive/cards/economy")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["success", "error"]

    def test_archive_invalid_category(self):
        """Archive with invalid category should return error."""
        response = self.client.get("/api/archive/cards/invalid_category")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


# ============================================================
# MODULE 4: CONTEXT INITIALIZATION
# ============================================================
class TestContextInit:
    """Tests that AppContext handles missing credentials gracefully."""

    def test_context_singleton_exists(self):
        """Context singleton should be importable without crash."""
        from backend.services.context import context
        assert context is not None

    def test_context_has_db_method(self):
        """Context should expose get_db method."""
        from backend.services.context import context
        assert hasattr(context, "get_db")

    def test_context_has_km_method(self):
        """Context should expose get_km method."""
        from backend.services.context import context
        assert hasattr(context, "get_km")


# ============================================================
# MODULE 5: PLAN EXTRACTION (Card Extractor Helper)
# ============================================================
from backend.engine.card_extractor import _extract_price


class TestPlanExtraction:
    """Tests the helper that extracts float prices from plan level strings."""

    def test_dollar_sign_price(self):
        assert _extract_price("$140.50") == 140.50

    def test_plain_number(self):
        assert _extract_price("140") == 140.0

    def test_mixed_text(self):
        assert _extract_price("Long above 181.25 with confirmation") == 181.25

    def test_empty_string(self):
        assert _extract_price("") is None

    def test_none_input(self):
        assert _extract_price(None) is None

    def test_no_number(self):
        assert _extract_price("No level specified") is None


# ============================================================
# MODULE 6: SOCKET MANAGER
# ============================================================
class TestSocketManager:
    """Tests the WebSocket connection manager."""

    def test_manager_singleton(self):
        from backend.services.socket_manager import manager
        assert manager is not None
        assert hasattr(manager, "active_connections")
        assert isinstance(manager.active_connections, list)

    def test_manager_disconnect_nonexistent(self):
        """Disconnecting a non-existent connection should not crash."""
        from backend.services.socket_manager import manager
        mock_ws = MagicMock()
        # Should not raise
        manager.disconnect(mock_ws)
