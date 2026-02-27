import asyncio
import json
import logging
import time
import websockets
from typing import Dict, List, Optional, Set
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
        self.on_price_update = None # Callback function(ticker, price_data)

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
        self.tickers = set(tickers)
        if self.running and self.ws:
            asyncio.create_task(self._sync_subscriptions())

    async def _run_loop(self):
        while self.running:
            try:
                self.cst, self.xst = create_capital_session_v2()
                if not self.cst or not self.xst:
                    log.error("Capital WS: Auth failed. Retrying in 10s...")
                    await asyncio.sleep(10)
                    continue

                async with websockets.connect(self.URL) as websocket:
                    self.ws = websocket
                    log.info("✅ Capital WS: Connected.")
                    
                    # 2. Sync Subscriptions (Tokens are passed here)
                    await self._sync_subscriptions()

                    # 3. Listen for updates
                    while self.running:
                        message = await self.ws.recv()
                        data = json.loads(message)
                        self._handle_message(data)

            except Exception as e:
                log.error(f"Capital WS Error: {e}. Reconnecting in 5s...")
                self.ws = None
                self.subscriptions.clear()
                await asyncio.sleep(5)

    async def _sync_subscriptions(self):
        if not self.ws:
            return
            
        async with self._lock:
            # Simple diff to find new subscriptions
            # Capital.com EPICs are needed here.
            from backend.engine.processing import ticker_to_epic
            
            target_epics = {ticker_to_epic(t): t for t in self.tickers}
            
            # Store reverse map for broadcasting user tickers
            self._epic_to_ticker = target_epics
            
            # Unsubscribe from removed epics
            to_remove = self.subscriptions - set(target_epics.keys())
            for epic in to_remove:
                await self.ws.send(json.dumps({
                    "destination": "marketData.unsubscribe",
                    "cst": self.cst,
                    "securityToken": self.xst,
                    "payload": {"epics": [epic]}
                }))
                self.subscriptions.remove(epic)

            # Subscribe to new epics
            to_add = set(target_epics.keys()) - self.subscriptions
            if to_add:
                await self.ws.send(json.dumps({
                    "destination": "marketData.subscribe",
                    "cst": self.cst,
                    "securityToken": self.xst,
                    "payload": {"epics": list(to_add)}
                }))
                self.subscriptions.update(to_add)
                log.info(f"Capital WS: Subscribed to {list(to_add)}")

    def _handle_message(self, data):
        # Capital.com WS message structure:
        # {"destination": "quote", "payload": {"epic": "...", "bid": ..., "ofr": ...}}
        if data.get("destination") == "quote" or data.get("destination") == "market.update":
            payload = data.get("payload", {})
            epic = payload.get("epic")
            bid = payload.get("bid")
            ask = payload.get("ofr") or payload.get("ask")
            
            if epic and bid and ask:
                mid = (bid + ask) / 2
                self.prices[epic] = {"bid": bid, "ask": ask, "mid": mid, "ts": time.time()}
                
                # Resolve user ticker from epic (e.g. "US500" → "SPY")
                user_ticker = getattr(self, '_epic_to_ticker', {}).get(epic, epic)
                
                # Broadcast to all connected frontend clients
                from backend.services.socket_manager import manager
                import asyncio
                
                msg = {
                    "type": "PRICE_UPDATE",
                    "ticker": user_ticker,
                    "epic": epic,
                    "price": mid,
                    "bid": bid,
                    "ask": ask,
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(manager.broadcast_json(msg))
                except Exception:
                    pass

                if self.on_price_update:
                    self.on_price_update(user_ticker, self.prices[epic])

from datetime import datetime
# Global instance
capital_ws = CapitalWebSocketService()

