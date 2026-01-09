
# DUMMY KEYMANAGER (User Requested Direct API Access - No Database)

class KeyManager:
    def __init__(self, db_url, auth_token):
        # IGNORE DB CONNECTION
        pass

    def get_key(self, target_model: str, exclude_name=None, logger=None) -> tuple[str | None, str | None, float]:
        # Always return a dummy key, logic handled in gemini.py
        return "DirectKey", "DUMMY_KEY", 0.0

    def report_success(self, key: str, model_id: str):
        pass

    def report_failure(self, key: str, is_server_error=False):
        pass