import os
import toml
from infisical_client import InfisicalClient, ClientSettings, GetSecretOptions, AuthenticationOptions, UniversalAuthMethod

def debug_infisical():
    print("--- DEBUGGING INFISICAL ---")
    
    # 1. Load Creds
    client_id = os.getenv("INFISICAL_CLIENT_ID")
    client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
    project_id = os.getenv("INFISICAL_PROJECT_ID")

    if not client_id:
        try:
            print("Loading from secrets.toml...")
            data = toml.load(".streamlit/secrets.toml")
            sec = data.get("infisical", {})
            client_id = sec.get("client_id")
            client_secret = sec.get("client_secret")
            project_id = sec.get("project_id")
        except Exception as e:
            print(f"Failed to load secrets.toml: {e}")

    print(f"Client ID Present: {bool(client_id)}")
    print(f"Project ID: {project_id}")

    if not client_id or not client_secret:
        print("❌ Credentials Missing")
        return

    # 2. Connect
    try:
        auth_method = UniversalAuthMethod(client_id=client_id, client_secret=client_secret)
        options = AuthenticationOptions(universal_auth=auth_method)
        client = InfisicalClient(ClientSettings(auth=options))
        print("✅ Client Initialized")
    except Exception as e:
        print(f"❌ Auth Failed: {e}")
        return

    # 3. Try to List/Get Secrets
    # We will try the exact names we expect
    targets = [
        "capital_com_X_CAP_API_KEY",
        "capital_com_IDENTIFIER",
        "capital_com_PASSWORD",
        "CAPITAL_X_CAP_API_KEY", 
        "turso_emadarshadalam_newsdatabase_DB_URL"
    ]

    environments = ["dev", "prod"]
    
    for env in environments:
        print(f"\n--- Checking Environment: {env} ---")
        for name in targets:
            try:
                secret = client.getSecret(options=GetSecretOptions(
                    secret_name=name,
                    project_id=project_id,
                    environment=env,
                    path="/"
                ))
                print(f"   ✅ FOUND in {env}: {name}")
            except Exception:
                print(f"   ❌ FAILED in {env}: {name}")

if __name__ == "__main__":
    debug_infisical()
