from modules.infisical_manager import InfisicalManager
import os
import toml

def test_infisical():
    print("Testing Infisical Connection...")
    mgr = InfisicalManager()
    if not mgr.is_connected:
        print("❌ Infisical not connected.")
        # Check why
        if not os.path.exists(".streamlit/secrets.toml"):
             print("Missing .streamlit/secrets.toml")
        else:
             print(".streamlit/secrets.toml exists.")
        return

    print("✅ Infisical Connected.")
    
    # Try expected secrets
    db_url = mgr.get_secret("turso_emadprograms_analystworkbench_DB_URL")
    auth_token = mgr.get_secret("turso_emadprograms_analystworkbench_AUTH_TOKEN")
    
    if db_url and auth_token:
        print(f"✅ Found secrets. URL: {db_url[:20]}...")
        import libsql_client
        try:
            url = db_url.replace("libsql://", "https://")
            client = libsql_client.create_client_sync(url=url, auth_token=auth_token)
            print("✅ Database Connection Successful!")
            rs = client.execute("SELECT 1")
            print(f"✅ Query Result: {rs.rows}")
            client.close()
        except Exception as e:
            print(f"❌ Database Connection Failed: {e}")
    else:
        print("❌ Secrets not found.")

if __name__ == "__main__":
    test_infisical()
