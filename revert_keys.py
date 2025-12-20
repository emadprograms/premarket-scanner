import os
import libsql_client

def main():
    print("--- REVERTING KEYS TO CORRECT TIERS ---")
    
    # HARDCODED CREDENTIALS FROM SECRETS
    db_url = "libsql://analyst-workbench-database-emadarshadalam.aws-ap-south-1.turso.io"
    auth_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NjI1MjIwMDMsImlkIjoiMTA5NjAzY2QtYzhkZi00OTE3LWIwZTItMDgzNjFmMjFkZTUwIiwicmlkIjoiZjcxOTdhOTgtYjViZS00NmY3LTk2YmQtMWNjZjNlYTRlMWQ5In0.hU4LWQ43wbsptdK_KLF7je8RxoCKgZ20WJL5aOMpcV4NbnnQhIYe60rBGoQJzTXiIhDEoCas9Ai7LuybrhCPCQ"
    
    if "libsql://" in db_url:
        db_url = db_url.replace("libsql://", "https://")

    print(f"Connecting to: {db_url}")
    
    try:
        client = libsql_client.create_client_sync(url=db_url, auth_token=auth_token)
        
        # 1. Reset ALL to 'free'
        client.execute("UPDATE gemini_api_keys SET tier = 'free'")
        print("✅ Reset all keys to 'free'.")
        
        # 2. Set only 'arshad.emad@01' to 'paid'
        target_key = "arshad.emad@01"
        client.execute("UPDATE gemini_api_keys SET tier = 'paid' WHERE key_name = ?", [target_key])
        
        # Verify
        rs_paid = client.execute("SELECT COUNT(*) FROM gemini_api_keys WHERE tier = 'paid'")
        count_paid = rs_paid.rows[0][0]
        
        rs_free = client.execute("SELECT COUNT(*) FROM gemini_api_keys WHERE tier = 'free'")
        count_free = rs_free.rows[0][0]
        
        print(f"✅ Verification:")
        print(f"   - Paid Keys: {count_paid} (Should be 1)")
        print(f"   - Free Keys: {count_free}")

        if count_paid == 1:
            print("🎉 SUCCESS: DB Tiers Restored.")
        else:
            print(f"⚠️ WARNING: Found {count_paid} paid keys. Check key name exact spelling.")
            
            # Debug: List paid keys
            rs = client.execute("SELECT key_name FROM gemini_api_keys WHERE tier='paid'")
            for r in rs.rows:
                print(f"   Examples: {r[0]}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
