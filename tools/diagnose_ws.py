import asyncio
import json
import sys
import os

# Ensure the backend module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets
from backend.engine.capital_api import create_capital_session_v2
from backend.engine.processing import ticker_to_epic

# The 19 specific tickers you provided
TICKERS = [
    "AAPL", "ADBE", "AMD", "AMZN", "APP", "AVGO", "BABA", "GOOGL", "LRCX",
    "META", "MSFT", "MU", "NVDA", "ORCL", "PANW", "QCOM", "SHOP", "TSLA", "TSM"
]

WS_URL = "wss://api-streaming-capital.backend-capital.com/connect"

async def diagnose_capital_ws():
    print(f"🔍 Starting Capital.com WebSocket Diagnostic for {len(TICKERS)} tickers...")
    
    # 1. Map tickers to epics
    epics = []
    epic_to_ticker_map = {}
    for ticker in TICKERS:
        epic = ticker_to_epic(ticker)
        epics.append(epic)
        epic_to_ticker_map[epic] = ticker
        print(f"   Mapped {ticker} -> {epic}")

    # 2. Authenticate via REST to get tokens
    print("\n🔐 Authenticating with Capital.com via REST API...")
    cst, xst = create_capital_session_v2()
    
    if not cst or not xst:
        print("❌ Authentication Failed. Check your Infisical secrets:")
        print("   - capital_com_X_CAP_API_KEY")
        print("   - capital_com_IDENTIFIER")
        print("   - capital_com_PASSWORD")
        return

    print("✅ Authentication Successful. Got CST and X-SECURITY-TOKEN.")

    # 3. Connect to WebSocket
    print(f"\n🌐 Connecting to {WS_URL}...")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✅ WebSocket Connected.")
            
            # 4. Send Subscription Payload with Tokens
            print(f"📡 Sending Market Subscription Payload for {len(epics)} epics...")
            sub_payload = {
                "destination": "marketData.subscribe",
                "correlationId": "1",
                "cst": cst,
                "securityToken": xst,
                "payload": {
                    "epics": epics
                }
            }
            await websocket.send(json.dumps(sub_payload))
            
            print("\n🎧 Listening for Market Updates (Waiting 10 seconds)...\n")
            print("-" * 50)
            
            # 6. Listen and format incoming data for 10 seconds
            end_time = asyncio.get_event_loop().time() + 10.0
            updates_received = 0
            while True:
                if asyncio.get_event_loop().time() > end_time:
                    break
                
                # Use wait_for to prevent blocking forever if no messages arrive
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    # Check if it's a market update
                    if data.get("destination") == "market.update":
                        payload = data.get("payload", {})
                        epic = payload.get("epic")
                        bid = payload.get("bid")
                        ask = payload.get("ask")
                        
                        if epic and bid and ask:
                            updates_received += 1
                            ticker = epic_to_ticker_map.get(epic, epic)
                            mid = (bid + ask) / 2
                            print(f"📈 UPDATE | {ticker:<6} | Bid: {bid:>8.2f} | Ask: {ask:>8.2f} | Mid: {mid:>8.2f}")
                    else:
                        # Print system/ping messages
                        print(f"⚙️ SYSTEM | {data}")
                except asyncio.TimeoutError:
                    continue

            print("-" * 50)
            print(f"✅ Diagnostic Complete. Received {updates_received} market updates in 10 seconds.")

    except Exception as e:
        print(f"\n❌ WebSocket Connection Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(diagnose_capital_ws())
    except KeyboardInterrupt:
        print("\n🛑 Diagnostic stopped by user.")