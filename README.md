# Pre-Market Proximity Scanner

A real-time tradability ranking engine for financial assets. The system monitors live price action relative to structural trade plans and ranks tickers based on normalized proximity to Key Levels (Plan A and Plan B).

## Architecture

- **Pre-Market Scanner (The Cockpit)**: Real-time proximity ranking engine using Capital.com WebSockets and ATR-normalized distance calculations.
- **Archive Room**: A separate interface for managing and viewing historical/EOD company cards and economic structural plans.

## Core Principles

- **Mathematical Ranking**: No AI. Cards are ranked purely on the distance from price to plan levels.
- **WebSocket Aggregator**: Persistent real-time streaming for Bid/Ask/Mid prices.
- **ATR Normalization**: Volatility-adjusted proximity allows fair comparison between stocks of different price tiers.
- **Decoupled Identity**: Scanner and Archive Room are isolated programs.

## Setup

1.  **Environment**: Requires Python 3.12.
2.  **Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Secrets**: Configure Turso DB, Capital.com, and Gemini API keys (for plan generation) in Infisical or `.env`.

## Execution

- **Backend (FastAPI)**:
    ```bash
    python3 -m uvicorn backend.main:app --port 8000
    ```
- **Frontend (Next.js)**:
    ```bash
    cd frontend && npm run dev
    ```
