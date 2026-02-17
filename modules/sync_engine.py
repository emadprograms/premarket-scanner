import sqlite3
import json
import os
from datetime import datetime

def sync_turso_to_local(turso_client, local_db_path, logger):
    """
    Downloads key tables from Turso to a local SQLite database atomically.
    """
    temp_db_path = local_db_path + ".tmp"
    essential_tables = ["stocks", "company_cards", "economy_cards", "symbol_map"]
    
    try:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
            
        logger.log(f"Sync: Initializing essential sync to {temp_db_path}...")
        local_conn = sqlite3.connect(temp_db_path)
        
        # 1. Sync Essential Tables
        for table in essential_tables:
            logger.log(f"Sync: Downloading '{table}'...")
            rs = turso_client.execute(f"SELECT * FROM {table}")
            cols = [col for col in rs.columns]
            
            # Robust schema creation
            col_defs = ", ".join([f'"{c}"' for c in cols])
            local_conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs})')
            
            if rs.rows:
                local_conn.executemany(
                    f'INSERT INTO "{table}" VALUES ({", ".join(["?"] * len(cols))})',
                    rs.rows
                )
                logger.log(f"  ✅ '{table}': {len(rs.rows)} rows.")

        local_conn.commit()
        
        # 2. Finalize Essential DB before attempting risky market_data
        local_conn.close()
        if os.path.exists(local_db_path):
            os.remove(local_db_path)
        os.rename(temp_db_path, local_db_path)
        logger.log("✅ Essential Tables Synced (System is now functional).")

        # 3. Attempt Market Data (Granular Sync by Ticker)
        try:
            logger.log("Sync: Starting Granular Market Data Sync (Last 7 Days)...")
            local_conn = sqlite3.connect(local_db_path)
            
            # Schema first
            rs_schema = turso_client.execute("SELECT * FROM market_data LIMIT 0")
            cols = [col for col in rs_schema.columns]
            col_defs = ", ".join([f'"{c}"' for c in cols])
            local_conn.execute(f'CREATE TABLE IF NOT EXISTS "market_data" ({col_defs})')
            
            # We sync the core tickers first to ensure the app works
            # Using a list derived from the 22 tickers we identified
            core_tickers = [
                "BTCUSDT", "CL=F", "DIA", "EURUSDT", "IWM",
                "PAXGUSDT", "QQQ", "SMH", "SPY", "TLT",
                "UUP", "XLC", "XLF", "XLI", "XLP",
                "XLU", "XLV", "XLK", "XLE", "GLD", "NDAQ", "^VIX"
            ]

            for ticker in core_tickers:
                try:
                    logger.log(f"  Sync: Fetching '{ticker}' (7d)...")
                    # Fetch in one go per ticker (usually < 10k rows, safe for Turso)
                    # We use a date filter to keep it manageable and hit the user's Feb 12th target
                    query = f"SELECT * FROM market_data WHERE symbol = ? AND timestamp > date('now', '-7 days')"
                    rs = turso_client.execute(query, [ticker])
                    
                    if rs.rows:
                        # Clean old data for this ticker to avoid duplicates if re-syncing
                        local_conn.execute('DELETE FROM market_data WHERE symbol = ?', [ticker])
                        
                        local_conn.executemany(
                            f'INSERT INTO "market_data" VALUES ({", ".join(["?"] * len(cols))})',
                            rs.rows
                        )
                        logger.log(f"    ✅ '{ticker}': {len(rs.rows)} rows.")
                    else:
                        logger.log(f"    ⚠️ '{ticker}': No data found in last 7 days.")
                except Exception as ticker_err:
                    logger.log(f"    ❌ '{ticker}' failed: {ticker_err}")

            local_conn.commit()
            local_conn.close()
            logger.log("✅ Market Data Sync Complete.")
        except Exception as e:
            logger.log(f"⚠️ Market Data Sync skipped/failed: {e}")
            if 'local_conn' in locals(): local_conn.close()
            
        return True

        rs = turso_client.execute("SELECT * FROM market_data WHERE datetime > date('now', '-30 days')")
        if rs.rows:
            logger.log(f"Sync: Writing {len(rs.rows)} rows to 'market_data'...")
            local_conn.executemany(
                f"INSERT INTO market_data VALUES ({', '.join(['?'] * len(cols))})",
                rs.rows
            )

        local_conn.commit()
        local_conn.close()
        
        # Atomic Rename
        if os.path.exists(local_db_path):
            os.remove(local_db_path)
        os.rename(temp_db_path, local_db_path)
        
        logger.log(f"✅ Sync Successful: {local_db_path} updated.")
        return True
    except Exception as e:
        logger.log(f"❌ Sync Error: {e}")
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
        return False
