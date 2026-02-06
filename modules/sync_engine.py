import sqlite3
import json
import os
from datetime import datetime

def sync_turso_to_local(turso_client, local_db_path, logger):
    """
    Downloads key tables from Turso to a local SQLite database.
    Tables to sync: 
    1. Stocks
    2. company_cards
    3. economy_cards
    4. symbol_map
    """
    try:
        if os.path.exists(local_db_path):
            os.remove(local_db_path)
            
        local_conn = sqlite3.connect(local_db_path)
        
        # 1. Sync Stocks
        logger.log("Sync: Downloading 'Stocks' table...")
        rs = turso_client.execute("SELECT * FROM Stocks")
        cols = [col for col in rs.columns]
        local_conn.execute(f"CREATE TABLE Stocks ({', '.join(cols)})")
        local_conn.executemany(
            f"INSERT INTO Stocks VALUES ({', '.join(['?'] * len(cols))})",
            rs.rows
        )

        # 2. Sync company_cards
        logger.log("Sync: Downloading 'company_cards' table...")
        rs = turso_client.execute("SELECT * FROM company_cards")
        cols = [col for col in rs.columns]
        local_conn.execute(f"CREATE TABLE company_cards ({', '.join(cols)})")
        local_conn.executemany(
            f"INSERT INTO company_cards VALUES ({', '.join(['?'] * len(cols))})",
            rs.rows
        )

        # 3. Sync economy_cards
        logger.log("Sync: Downloading 'economy_cards' table...")
        rs = turso_client.execute("SELECT * FROM economy_cards")
        cols = [col for col in rs.columns]
        local_conn.execute(f"CREATE TABLE economy_cards ({', '.join(cols)})")
        local_conn.executemany(
            f"INSERT INTO economy_cards VALUES ({', '.join(['?'] * len(cols))})",
            rs.rows
        )

        # 4. Sync symbol_map
        logger.log("Sync: Downloading 'symbol_map' table...")
        rs = turso_client.execute("SELECT * FROM symbol_map")
        cols = [col for col in rs.columns]
        local_conn.execute(f"CREATE TABLE symbol_map ({', '.join(cols)})")
        local_conn.executemany(
            f"INSERT INTO symbol_map VALUES ({', '.join(['?'] * len(cols))})",
            rs.rows
        )

        # 5. Sync market_data (Optional/Sampled? Large table)
        # For testing, we might only need recent data. 
        # But let's sync the whole table if it's not too massive, or filter by date.
        # User wants "rigorous testing", so let's try to get it all, or the last 30 days.
        logger.log("Sync: Downloading 'market_data' (last 30 days)...")
        rs = turso_client.execute("SELECT * FROM market_data WHERE datetime > date('now', '-30 days')")
        cols = [col for col in rs.columns]
        local_conn.execute(f"CREATE TABLE market_data ({', '.join(cols)})")
        local_conn.executemany(
            f"INSERT INTO market_data VALUES ({', '.join(['?'] * len(cols))})",
            rs.rows
        )

        local_conn.commit()
        local_conn.close()
        logger.log(f"Sync: Successfully created {local_db_path}")
        return True
    except Exception as e:
        logger.log(f"Sync Error: {e}")
        return False
