import asyncio
import json
import logging
import time
import websockets
from typing import Dict, List, Optional, Set
from datetime import datetime
from backend.engine.capital_api import create_capital_session_v2

log = logging.getLogger(__name__)

class CapitalWebSocketService:
    """
    Singleton service that manages a persistent WebSocket connection to Capital.com.
    Aggregates BID/ASK prices for all watchlist tickers and broadcasts them.
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
        self._pending_tickers: Set[str] = set()  # Tickers queued before WS is ready
        self._update_count = 0
        self.on_price_update = None

    async def start(self):
        """Starts the background connection task."""
        if self.running:
            return
        self.running = True
        asyncio.create_task(self._run_loop())

    async def stop(self):
        self.running = False
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

    async def _run_loop(self):
        while self.running:
            # Don't connect until we actually have tickers to subscribe to
            if not self.tickers and not self._pending_tickers:
                log.debug("Capital WS: No tickers set. Waiting for subscription request...")
                await asyncio.sleep(5)
                continue

            try:
                log.info("Capital WS: Authenticating...")
                self.cst, self.xst = create_capital_session_v2()
                if not self.cst or not self.xst:
                    log.error("Capital WS: Auth failed. Retrying in 10s...")
                    await asyncio.sleep(10)
                    continue

                log.info("Capital WS: Auth OK. Connecting to stream...")
                async with websockets.connect(self.URL) as websocket:
                    self.ws = websocket
                    log.info("✅ Capital WS: Connected.")
                    
                    # Subscribe to any pending tickers
                    if self._pending_tickers or self.tickers:
                        await self._sync_subscriptions()

                    # Listen for updates
                    while self.running:
                        try:
                            message = await asyncio.wait_for(self.ws.recv(), timeout=30)
                            data = json.loads(message)
                            await self._handle_message(data)
                        except asyncio.TimeoutError:
                            # No data in 30s — send application-level ping with auth tokens
                            if not self.subscriptions:
                                log.info("Capital WS: No active subscriptions. Idling...")
                                continue
                            log.warning("Capital WS: No data received in 30s. Sending app-level ping...")
                            try:
                                await self.ws.send(json.dumps({
                                    "destination": "ping",
                                    "correlationId": "PING",
                                    "cst": self.cst,
                                    "securityToken": self.xst,
                                }))
                                # Wait briefly for pong response
                                await asyncio.wait_for(self.ws.recv(), timeout=10)
                                log.info("Capital WS: Ping OK.")
                            except Exception:
                                log.warning("Capital WS: Ping failed. Reconnecting...")
                                break  # Exit inner loop to reconnect

            except Exception as e:
                log.error(f"Capital WS Error: {e}. Reconnecting in 5s...")
            finally:
                self.ws = None
                self.subscriptions.clear()
                if self.running:
                    await asyncio.sleep(5)

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
