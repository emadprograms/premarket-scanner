import os
import libsql_client

def get_env_var(name):
    # Try .env first or os.environ
    val = os.environ.get(name)
    if val: return val
    
    # Try manual parse of secrets.toml if env missing (local dev fallback)
    try:
        with open('.streamlit/secrets.toml', 'r') as f:
            content = f.read()
            import re
            match = re.search(f'{name}\s*=\s*"(.*?)"', content)
            if match: return match.group(1)
    except: pass
    return None

def main():
    print("--- UPDATING ALL KEYS TO 'PAID' TIER ---")
    
    # HARDCODED CREDENTIALS FROM SECRETS
    db_url = "libsql://analyst-workbench-database-emadarshadalam.aws-ap-south-1.turso.io"
    auth_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NjI1MjIwMDMsImlkIjoiMTA5NjAzY2QtYzhkZi00OTE3LWIwZTItMDgzNjFmMjFkZTUwIiwicmlkIjoiZjcxOTdhOTgtYjViZS00NmY3LTk2YmQtMWNjZjNlYTRlMWQ5In0.hU4LWQ43wbsptdK_KLF7je8RxoCKgZ20WJL5aOMpcV4NbnnQhIYe60rBGoQJzTXiIhDEoCas9Ai7LuybrhCPCQ"
    
    if not db_url or not auth_token:
        # Fallback hardcoded for user convenience if script fails to find them
        # (Based on previous verify script output which had url, but token hidden)
        print("❌ Could not find credentials in environment or secrets.toml")
        return

    if "libsql://" in db_url:
        db_url = db_url.replace("libsql://", "https://")

    print(f"Connecting to: {db_url}")
    
    try:
        client = libsql_client.create_client_sync(url=db_url, auth_token=auth_token)
        
        # 1. Update all to paid
        client.execute("UPDATE gemini_api_keys SET tier = 'paid'")
        print("✅ Executed UPDATE statement.")
        
        # 2. Verify
        rs = client.execute("SELECT COUNT(*) FROM gemini_api_keys WHERE tier = 'paid'")
        count = rs.rows[0][0]
        print(f"✅ Verification: {count} keys are now set to 'paid'.")
        
        rs_total = client.execute("SELECT COUNT(*) FROM gemini_api_keys")
        total = rs_total.rows[0][0]
        print(f"📊 Total keys in DB: {total}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
