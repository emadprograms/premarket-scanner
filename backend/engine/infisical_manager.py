import os
import toml
from infisical_client import InfisicalClient, ClientSettings, GetSecretOptions, AuthenticationOptions, UniversalAuthMethod

class InfisicalManager:
    def __init__(self):
        self.client = None
        self.is_connected = False
        
        # Load from Env or Secrets file
        client_id = os.getenv("INFISICAL_CLIENT_ID")
        client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
        self.project_id = os.getenv("INFISICAL_PROJECT_ID")
        self.infisical_env = os.getenv("INFISICAL_ENV") or "dev"
        
        if not client_id:
            try:
                # Fallback to manual TOML if not in environment
                secrets_path = os.path.join(os.getcwd(), ".streamlit/secrets.toml")
                if os.path.exists(secrets_path):
                    data = toml.load(secrets_path)
                    sec = data.get("infisical", {})
                    client_id = sec.get("client_id")
                    client_secret = sec.get("client_secret")
                    self.project_id = sec.get("project_id")
                    print(f"[DEBUG] Loaded Infisical config from {secrets_path}")
            except Exception as e:
                print(f"[DEBUG] Infisical config load error: {e}")
        
        if client_id and client_secret:
            try:
                auth_method = UniversalAuthMethod(client_id=client_id, client_secret=client_secret)
                options = AuthenticationOptions(universal_auth=auth_method)
                self.client = InfisicalClient(ClientSettings(auth=options))
                self.is_connected = True
                print(f"[OK] Infisical Connected (Project: {self.project_id}, Env: {self.infisical_env})")
            except Exception as e:
                print(f"[ERROR] Infisical Auth Failed: {e}")
        else:
            print("[INFO] Infisical Credentials Missing (optional, falling back to direct environment variables)")

    def list_secrets(self, path="/", environment="dev"):
        if not self.is_connected: return []
        try:
            from infisical_client import ListSecretsOptions
            secrets = self.client.listSecrets(options=ListSecretsOptions(
                project_id=self.project_id,
                environment=environment,
                path=path,
                attach_to_process_env=False,
                include_imports=True
            ))
            return secrets
        except Exception as e:
            print(f"[ERROR] Failed to list secrets: {e}")
            return []

    def get_secret(self, secret_name):
        if not self.is_connected: return os.getenv(secret_name)
        try:
            # NOTE: Use snake_case for options
            secret = self.client.getSecret(options=GetSecretOptions(
                secret_name=secret_name,
                project_id=self.project_id,
                environment=self.infisical_env,
                path="/"
            ))
            return getattr(secret, "secret_value", getattr(secret, "secretValue", None)) 
        except Exception as e:
            # Fallback to standard environment variable
            return os.getenv(secret_name)

    def get_secret_ext(self, secret_name, environment):
        if not self.is_connected: return os.getenv(secret_name)
        try:
            secret = self.client.getSecret(options=GetSecretOptions(
                secret_name=secret_name,
                project_id=self.project_id,
                environment=environment,
                path="/"
            ))
            
            # SDK returns objects or dicts depending on version
            if isinstance(secret, dict):
                return secret.get("secret_value", secret.get("secretValue"))
            return getattr(secret, "secret_value", getattr(secret, "secretValue", None))
        except Exception as e:
            print(f"[DEBUG] get_secret_ext('{secret_name}', '{environment}'): {e}")
            return None
