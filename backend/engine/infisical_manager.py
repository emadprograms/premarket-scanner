import os
import logging
from infisical_sdk import InfisicalSDKClient

log = logging.getLogger(__name__)

class InfisicalManager:
    """
    MODERN INFISICAL SDK MANAGER (SDK V2 - infisicalsdk)
    Singleton that manages client connection, authentication and secret retrieval.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(InfisicalManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.client = None
        self.is_connected = False
        
        # Load credentials from Environment (Standard Deployment)
        self.client_id = os.getenv("INFISICAL_CLIENT_ID")
        self.client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
        self.project_id = os.getenv("INFISICAL_PROJECT_ID")
        self.infisical_env = os.getenv("INFISICAL_ENV", "dev")

        if self.client_id and self.client_secret:
            self._connect()

    def _connect(self):
        """Initializes and authenticates the Infisical SDK Client."""
        try:
            self.client = InfisicalSDKClient(host="https://app.infisical.com")
            
            # Universal Auth (Modern Pattern)
            self.client.auth.universal_auth.login(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            
            self.is_connected = True
            log.info(f"✅ Infisical: SDK Connected (Project: {self.project_id}, Env: {self.infisical_env})")
        except Exception as e:
            log.error(f"❌ Infisical Connection Error: {e}")
            self.is_connected = False

    def get_secret_ext(self, secret_name: str, environment: str = None) -> str:
        """Retrieves a secret from the specified environment (defaulting to self.infisical_env)."""
        if not self.is_connected or not self.client:
            return None
            
        try:
            target_env = environment if environment else self.infisical_env
            secret = self.client.secrets.get_secret_by_name(
                secret_name=secret_name,
                environment_slug=target_env,
                secret_path="/",
                project_id=self.project_id
            )
            # SDK V2 uses secretValue
            return getattr(secret, "secretValue", None)
        except Exception as e:
            log.debug(f"ℹ️ Infisical: Secret '{secret_name}' not found in '{target_env}': {e}")
            return None

    def get_secret(self, secret_name: str, environment: str = None) -> str:
        """Alias for get_secret_ext for backward compatibility."""
        return self.get_secret_ext(secret_name, environment)

    def list_secrets(self, path: str = "/", environment: str = None) -> list:
        """Lists all secrets in a given path and environment."""
        if not self.is_connected or not self.client:
            return []
            
        try:
            target_env = environment if environment else self.infisical_env
            resp = self.client.secrets.list_secrets(
                environment_slug=target_env,
                secret_path=path,
                project_id=self.project_id,
                include_imports=True
            )
            # list_secrets returns a ListSecretsResponse, we want the secrets list
            return getattr(resp, "secrets", [])
        except Exception as e:
            log.error(f"❌ Infisical: Failed to list secrets: {e}")
            return []
