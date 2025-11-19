# src/external_services/database/connection.py

import libsql_client
from libsql_client import create_client_sync, LibsqlError
from src.config.credentials import load_turso_config

def create_turso_client(log_func) -> libsql_client.Client | None:
    """
    Creates and returns a Turso DB client.
    Accepts a log_func to send status messages back to the caller.
    """
    url, token = load_turso_config()
    if not url or not token:
        log_func("DB Error: Turso URL or Auth Token missing in credentials.")
        return None

    try:
        client = create_client_sync(url=url, auth_token=token)
        log_func("DB: Turso client created successfully.")
        return client
    except LibsqlError as e:
        log_func(f"DB Error (Libsql): Failed to create client: {e}")
        return None
    except Exception as e:
        log_func(f"DB Error (Unknown): Failed to create client: {e}")
        return None
