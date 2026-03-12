"""
Tests for Capital.com WebSocket Keepalive Logic
================================================
Tests the heartbeat, token expiry, and ping validation logic
in CapitalWebSocketService without requiring a live connection.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.capital_socket import (
    CapitalWebSocketService,
    HEARTBEAT_INTERVAL,
    TOKEN_MAX_AGE,
)


# Reset the singleton before each test
@pytest.fixture(autouse=True)
def reset_singleton():
    CapitalWebSocketService._instance = None
    yield
    CapitalWebSocketService._instance = None


@pytest.fixture
def service():
    svc = CapitalWebSocketService()
    svc.cst = "test_cst"
    svc.xst = "test_xst"
    svc._auth_time = time.time()
    return svc


# ------------------------------------------------------------------
# Token Expiry Detection
# ------------------------------------------------------------------
class TestTokenExpiry:
    """Verify that token age is tracked and expired tokens are detected."""

    def test_fresh_tokens_not_expired(self, service):
        """Tokens obtained just now should NOT be expired."""
        assert service._tokens_expired() is False

    def test_old_tokens_expired(self, service):
        """Tokens older than TOKEN_MAX_AGE should be expired."""
        service._auth_time = time.time() - TOKEN_MAX_AGE - 1
        assert service._tokens_expired() is True

    def test_zero_auth_time_is_expired(self, service):
        """Default auth_time of 0 (never authenticated) should be expired."""
        service._auth_time = 0
        assert service._tokens_expired() is True

    def test_tokens_just_before_expiry_not_expired(self, service):
        """Tokens just under the threshold should still be valid."""
        service._auth_time = time.time() - TOKEN_MAX_AGE + 30  # 30s before expiry
        assert service._tokens_expired() is False


# ------------------------------------------------------------------
# Ping Response Validation
# ------------------------------------------------------------------
class TestPingValidation:
    """
    The heartbeat loop must distinguish valid pong responses from
    error/auth-failure responses. These tests simulate the JSON the
    server would send back and verify the service handles them correctly.
    """

    @pytest.mark.asyncio
    async def test_error_destination_triggers_reconnect(self, service):
        """A response with destination containing 'error' should force reconnect."""
        mock_ws = AsyncMock()
        service.ws = mock_ws
        service.running = True

        # Simulate: send succeeds, recv returns an error payload
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps({
            "destination": "error",
            "status": "error",
            "payload": {"errorCode": "error.invalid.token"}
        }))
        mock_ws.close = AsyncMock()

        # Run one heartbeat iteration (it should break after detecting the error)
        with patch("backend.engine.capital_api.clear_capital_session") as mock_clear:
            # Override sleep to avoid waiting
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await service._heartbeat_loop()
            mock_clear.assert_called_once()
        mock_ws.close.assert_called()

    @pytest.mark.asyncio
    async def test_valid_pong_does_not_reconnect(self, service):
        """A clean pong response should NOT trigger reconnect."""
        mock_ws = AsyncMock()
        service.ws = mock_ws
        service.running = True

        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                service.running = False  # Stop after 2 iterations

        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps({
            "destination": "heartbeat",
            "status": "ok",
        }))
        mock_ws.close = AsyncMock()

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await service._heartbeat_loop()

        # close should NOT have been called by the heartbeat (only loop exit)
        mock_ws.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_triggers_reconnect(self, service):
        """If no pong is received within PING_RESPONSE_TIMEOUT, force reconnect."""
        mock_ws = AsyncMock()
        service.ws = mock_ws
        service.running = True

        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_ws.close = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await service._heartbeat_loop()

        mock_ws.close.assert_called()


# ------------------------------------------------------------------
# Price Message Handling
# ------------------------------------------------------------------
class TestMessageHandling:
    """Verify that normal price update messages are still processed correctly."""

    @pytest.mark.asyncio
    async def test_quote_message_updates_prices(self, service):
        """A valid quote message should populate the prices dict."""
        service._epic_to_ticker = {"AAPL_EPIC": "AAPL"}

        with patch("backend.services.socket_manager.manager") as mock_manager:
            mock_manager.broadcast_json = AsyncMock()

            await service._handle_message({
                "destination": "quote",
                "payload": {
                    "epic": "AAPL_EPIC",
                    "bid": 150.0,
                    "ofr": 150.10,
                }
            })

        assert "AAPL_EPIC" in service.prices
        assert service.prices["AAPL_EPIC"]["mid"] == pytest.approx(150.05)
        assert service.prices["AAPL_EPIC"]["bid"] == 150.0
        assert service.prices["AAPL_EPIC"]["ask"] == 150.10

    @pytest.mark.asyncio
    async def test_heartbeat_message_ignored(self, service):
        """Heartbeat messages should be silently consumed."""
        await service._handle_message({"destination": "heartbeat"})
        assert len(service.prices) == 0


# ------------------------------------------------------------------
# Auth Time Recording
# ------------------------------------------------------------------
class TestAuthTimeRecording:
    """Verify that _auth_time is set when new tokens are obtained."""

    def test_auth_time_defaults_to_zero(self):
        """A fresh service should have _auth_time == 0 (never authenticated)."""
        svc = CapitalWebSocketService()
        assert svc._auth_time == 0

    def test_tokens_expired_when_never_authenticated(self):
        """If _auth_time is 0, tokens should be considered expired."""
        svc = CapitalWebSocketService()
        assert svc._tokens_expired() is True
