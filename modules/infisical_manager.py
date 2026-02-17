import os
import toml
import streamlit as st
from infisical_client import InfisicalClient, ClientSettings, GetSecretOptions, AuthenticationOptions, UniversalAuthMethod

class InfisicalManager:
    def __init__(self):
        self.client = None
        self.is_connected = False
        
        # Load from Env or Secrets file
        client_id = os.getenv("INFISICAL_CLIENT_ID")
        client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
        self.project_id = os.getenv("INFISICAL_PROJECT_ID")
        
        if not client_id:
            try:
                # 1. Try Streamlit Secrets First (Native)
                sec = st.secrets.get("infisical", {})
                client_id = sec.get("client_id")
                client_secret = sec.get("client_secret")
                self.project_id = sec.get("project_id")
                
                # 2. Fallback to manual TOML if not in st.secrets
                if not client_id:
                    secrets_path = os.path.join(os.getcwd(), ".streamlit/secrets.toml")
                    if os.path.exists(secrets_path):
                        data = toml.load(secrets_path)
                        sec = data.get("infisical", {})
                        client_id = sec.get("client_id")
                        client_secret = sec.get("client_secret")
                        self.project_id = sec.get("project_id")
                        print(f"[DEBUG] Loaded from {secrets_path}")
            except Exception as e:
                print(f"[DEBUG] Load error: {e}")
        
        if client_id and client_secret:
            try:
                auth_method = UniversalAuthMethod(client_id=client_id, client_secret=client_secret)
                options = AuthenticationOptions(universal_auth=auth_method)
                self.client = InfisicalClient(ClientSettings(auth=options))
                self.is_connected = True
                print("[OK] Infisical Connected")
            except Exception as e:
                msg = f"Infisical Auth Failed: {e}"
                print(f"[ERROR] {msg}")
                st.error(msg)
        else:
            msg = "Infisical Credentials Missing (check secrets.toml or env)"
            print(f"[ERROR] {msg}")
            st.error(msg)

    def get_secret(self, secret_name):
        if not self.is_connected: return None
        try:
            # NOTE: Use snake_case for options
            secret = self.client.getSecret(options=GetSecretOptions(
                secret_name=secret_name,
                project_id=self.project_id,
                environment="dev",
                path="/"
            ))
            # NOTE: Use snake_case for attribute access (.secret_value, NOT .secretValue)
            return secret.secret_value 
        except Exception as e:
            print(f"[ERROR] Missing Secret: {secret_name}")
            return None
