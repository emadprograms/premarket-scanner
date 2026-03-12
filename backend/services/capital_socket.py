import asyncio
import json
import logging
import time
import websockets
from typing import Dict, List, Optional, Set
from datetime import datetime
from backend.engine.capital_api import create_capital_session_v2

log = logging.getLogger(__name__)

# Constants — tunable keepalive parameters
HEARTBEAT_INTERVAL = 25       # Seconds between proactive pings (Capital.com expects < 30s)
TOKEN_MAX_AGE = 45 * 60       # Force reconnect after 45 min (tokens expire ~60 min)
RECV_TIMEOUT = 30             # Seconds to wait for any message before fallback ping
PING_RESPONSE_TIMEOUT = 10    # Seconds to wait for a pong after sending a ping


class CapitalWebSocketService:
    """
    Singleton service that manages a persistent WebSocket connection to Capital.com.
    Aggregates BID/ASK prices for all watchlist tickers and broadcasts them.

    Keepalive strategy:
    - A background task sends a heartbeat ping every HEARTBEAT_INTERVAL seconds,
      regardless of whether data is flowing.
    - Ping responses are validated — any error or auth failure forces a full reconnect.
    - Tokens older than TOKEN_MAX_AGE trigger a proactive reconnect before they expire.
    """
    _instance = None
    URL = "wss://api-streaming-capital.backend-capital.com/connect"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CapitalWebSocketService, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.ws = None
        self.running = False
        self.tickers: Set[str] = set()
        self.prices: Dict[str, Dict[str, float]] = {}
        self.subscriptions: Set[str] = set()
        self.cst = None
        self.xst = None
        self._lock = asyncio.Lock()
        self._epic_to_ticker: Dict[str, str] = {}
        self._pending_tickers: Set[str] = set()
        self._update_count = 0
        self.on_price_update = None
        self._auth_time: float = 0  # Epoch when tokens were last obtained
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def start(self):
        """Starts the background connection task."""
        if self.running:
            return
        self.running = True
        asyncio.create_task(self._run_loop())

    async def stop(self):
        self.running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self.ws:
            await self.ws.close()

    def set_tickers(self, tickers: List[str]):
        """Update the set of tickers to monitor."""
        new_tickers = set(tickers)
        if new_tickers == self.tickers:
            return  # No change
        self.tickers = new_tickers
        self._pending_tickers = new_tickers.copy()
        if self.running and self.ws:
            asyncio.create_task(self._sync_subscriptions())
        else:
            log.info(f"Capital WS: Queued {len(tickers)} tickers (WS will connect when ready)")

    def _tokens_expired(self) -> bool:
        """Check if the current tokens are older than TOKEN_MAX_AGE."""
        if self._auth_time == 0:
            return True
        return (time.time() - self._auth_time) > TOKEN_MAX_AGE

    # ------------------------------------------------------------------
    # Heartbeat Task
    # ------------------------------------------------------------------
    async def _heartbeat_loop(self):
        """
        Proactive keepalive: sends a ping every HEARTBEAT_INTERVAL seconds
        regardless of whether data is flowing. Validates the response.
        """
        while self.running and self.ws:
            await asyncio.sleep(HEARTBEAT_INTERVAL)

            if not self.ws or not self.running:
                break

            # Token age check — force reconnect before they silently expire
            if self._tokens_expired():
                log.warning(f"Capital WS: Tokens are {int((time.time() - self._auth_time) / 60)}min old. "
                            f"Forcing reconnect for fresh auth.")
                try:
                    await self.ws.close()
                except Exception:
                    pass
                break

            # Send proactive ping
            try:
                await self.ws.send(json.dumps({
                    "destination": "ping",
                    "correlationId": "HEARTBEAT",
                    "cst": self.cst,
                    "securityToken": self.xst,
                }))
                response_raw = await asyncio.wait_for(self.ws.recv(), timeout=PING_RESPONSE_TIMEOUT)
                response = json.loads(response_raw) if isinstance(response_raw, str) else {}

                # Validate – check for error indicators in the response
                dest = response.get("destination", "")
                status = str(response.get("status", "")).lower()
                payload = response.get("payload", {})
                error_code = str(payload.get("errorCode", "")).lower() if isinstance(payload, dict) else ""

                is_error = (
                    "error" in dest.lower()
                    or "error" in status
                    or "invalid" in error_code
                    or "unauthorized" in error_code
                    or "expired" in error_code
                    or status in ("401", "403")
                )

                if is_error:
                    log.warning(f"Capital WS: Heartbeat rejected (dest={dest}, status={status}, "
                                f"errorCode={error_code}). Forcing reconnect...")
                    from backend.engine.capital_api import clear_capital_session
                    clear_capital_session()
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                    break
                else:
                    log.debug("Capital WS: Heartbeat OK.")

            except asyncio.TimeoutError:
                log.warning("Capital WS: Heartbeat response timed out. Forcing reconnect...")
                try:
                    await self.ws.close()
                except Exception:
                    pass
                break
            except websockets.exceptions.ConnectionClosed:
                log.warning("Capital WS: Connection closed during heartbeat. Will reconnect.")
                break
            except Exception as e:
                log.warning(f"Capital WS: Heartbeat failed ({e}). Forcing reconnect...")
                try:
                    await self.ws.close()
                except Exception:
                    pass
                break

    # ------------------------------------------------------------------
    # Main Connection Loop
    # ------------------------------------------------------------------
    async def _run_loop(self):
        reconnect_delay = 5  # Start at 5s, increase on repeated failures
        max_reconnect_delay = 60

        while self.running:
            # Don't connect until we actually have tickers to subscribe to
            if not self.tickers and not self._pending_tickers:
                log.debug("Capital WS: No tickers set. Waiting for subscription request...")
                await asyncio.sleep(5)
                continue

            try:
                log.info("Capital WS: Authenticating...")
                # Run blocking auth in thread pool to avoid freezing the event loop
                self.cst, self.xst = await asyncio.to_thread(create_capital_session_v2)
                if not self.cst or not self.xst:
                    log.error("Capital WS: Auth failed. Retrying in 10s...")
                    await asyncio.sleep(10)
                    continue

                self._auth_time = time.time()  # Record when we got fresh tokens
                log.info("Capital WS: Auth OK. Connecting to stream...")
                async with websockets.connect(self.URL) as websocket:
                    self.ws = websocket
                    log.info("✅ Capital WS: Connected.")
                    reconnect_delay = 5  # Reset backoff on successful connection

                    # Start the proactive heartbeat background task
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    # Subscribe to any pending tickers
                    if self._pending_tickers or self.tickers:
                        await self._sync_subscriptions()

                    # Listen for updates
                    while self.running:
                        try:
                            message = await asyncio.wait_for(self.ws.recv(), timeout=RECV_TIMEOUT)
                            data = json.loads(message)
                            await self._handle_message(data)
                        except asyncio.TimeoutError:
                            # No data in RECV_TIMEOUT — this is fine, the heartbeat task
                            # handles keepalive independently. Just loop back to recv().
                            if not self.subscriptions:
                                log.info("Capital WS: No active subscriptions. Idling...")
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            log.warning("Capital WS: Connection closed by server.")
                            break

            except Exception as e:
                log.error(f"Capital WS Error: {e}. Reconnecting in {reconnect_delay}s...")
            finally:
                # Clean up heartbeat task
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()
                    try:
                        await self._heartbeat_task
                    except asyncio.CancelledError:
                        pass
                self._heartbeat_task = None
                self.ws = None
                self.subscriptions.clear()
                if self.running:
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # Exponential backoff

    async def _sync_subscriptions(self):
        if not self.ws:
            return
            
        async with self._lock:
            from backend.engine.processing import ticker_to_epic
            
            target_epics = {ticker_to_epic(t): t for t in self.tickers}
            
            # Store reverse map for broadcasting user tickers
            self._epic_to_ticker = target_epics
            
            # Unsubscribe from removed epics
            to_remove = self.subscriptions - set(target_epics.keys())
            for epic in to_remove:
                try:
                    await self.ws.send(json.dumps({
                        "destination": "marketData.unsubscribe",
                        "correlationId": f"unsub_{epic}",
                        "cst": self.cst,
                        "securityToken": self.xst,
                        "payload": {"epics": [epic]}
                    }))
                    self.subscriptions.remove(epic)
                except Exception as e:
                    log.error(f"Capital WS: Failed to unsubscribe {epic}: {e}")

            # Subscribe to new epics
            to_add = set(target_epics.keys()) - self.subscriptions
            if to_add:
                try:
                    await self.ws.send(json.dumps({
                        "destination": "marketData.subscribe",
                        "correlationId": "sub_1",
                        "cst": self.cst,
                        "securityToken": self.xst,
                        "payload": {"epics": list(to_add)}
                    }))
                    self.subscriptions.update(to_add)
                    self._pending_tickers.clear()
                    log.info(f"✅ Capital WS: Subscribed to {len(to_add)} epics: {list(to_add)}")
                except Exception as e:
                    log.error(f"Capital WS: Failed to subscribe: {e}")

    async def _handle_message(self, data):
        """Handle incoming WebSocket messages from Capital.com."""
        dest = data.get("destination", "")
        
        if dest in ("quote", "market.update"):
            payload = data.get("payload", {})
            epic = payload.get("epic")
            bid = payload.get("bid")
            ask = payload.get("ofr") or payload.get("ask")
            
            if epic and bid and ask:
                mid = (bid + ask) / 2
                self.prices[epic] = {"bid": bid, "ask": ask, "mid": mid, "ts": time.time()}
                
                # Resolve user ticker from epic
                user_ticker = self._epic_to_ticker.get(epic, epic)
                
                # Broadcast to all connected frontend clients
                from backend.services.socket_manager import manager
                
                msg = {
                    "type": "PRICE_UPDATE",
                    "ticker": user_ticker,
                    "epic": epic,
                    "price": mid,
                    "bid": bid,
                    "ask": ask,
                    "timestamp": datetime.now().isoformat()
                }
                
                await manager.broadcast_json(msg)
                
                self._update_count += 1
                if self._update_count % 50 == 1:
                    log.info(f"📡 Capital WS: Price update #{self._update_count} — {user_ticker}=${mid:.2f}")
                
                if self.on_price_update:
                    self.on_price_update(user_ticker, self.prices[epic])
        elif dest == "heartbeat":
            pass  # Expected keepalive
        else:
            # Log unknown messages for debugging
            if self._update_count < 5:
                log.info(f"Capital WS msg: dest={dest}, keys={list(data.keys())}")

# Global instance
capital_ws = CapitalWebSocketService()
