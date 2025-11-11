import streamlit as st
import requests
from datetime import datetime, timezone

# ---
# --- AppLogger Class
# ---
class AppLogger:
    """A simple logger that writes to a Streamlit container."""
    def __init__(self, container):
        self.container = container
        self.log_messages = []

    def log(self, message: str):
        """Appends a new message to the log."""
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        new_msg = f"**{timestamp}Z:** {message}"
        self.log_messages.append(new_msg)
        
        # Display logs in reverse chronological order
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)

    def log_code(self, data, language='json'):
        """Appends a formatted code block to the log."""
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        new_msg = f"**{timestamp}Z:** (See code block below)"
        self.log_messages.append(new_msg)
        
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)
            if language == 'json' and isinstance(data, dict):
                self.container.json(data)
            else:
                self.container.code(str(data), language=language)

# ---
# --- Capital.com Authentication (UI Component)
# ---

def create_capital_session(logger: AppLogger) -> tuple[str | None, str | None]:
    """
    Creates a new session with Capital.com using st.secrets.
    Returns (cst_token, security_token) or (None, None) on failure.
    
    This function reads directly from st.secrets and does not
    depend on config.py.
    """
    logger.log("Attempting to create new Capital.com session...")
    capital_com_secrets = st.secrets.get("capital_com", {})
    api_key = capital_com_secrets.get("X_CAP_API_KEY")
    identifier = capital_com_secrets.get("identifier")
    password = capital_com_secrets.get("password")

    if not all([api_key, identifier, password]):
        logger.log("<span style='color:red;'>Error: Capital.com secrets not found.</span>")
        logger.log("Please add `[capital_com]` section to `.streamlit/secrets.toml`")
        return None, None
    
    # This URL is static for the session endpoint
    session_url = "https://api-capital.backend-capital.com/api/v1/session"
    headers = {'X-CAP-API-KEY': api_key, 'Content-Type': 'application/json'}
    payload = {"identifier": identifier, "password": password}
    
    try:
        response = requests.post(session_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        cst_token = response.headers.get('CST')
        security_token = response.headers.get('X-SECURITY-TOKEN')
        
        if cst_token and security_token:
            logger.log("<span style='color:green;'>Capital.com session created.</span>")
            return cst_token, security_token
        else:
            logger.log(f"Session failed: Tokens missing. Headers: {response.headers}")
            return None, None
            
    except requests.exceptions.HTTPError as e:
        logger.log(f"<span style='color:red;'>Session failed (HTTP Error): {e.response.status_code}</span>")
        try: 
            logger.log_code(e.response.json())
        except: 
            logger.log_code(e.response.text, 'text')
        return None, None
    except Exception as e:
        logger.log(f"<span style='color:red;'>Session failed (Error): {e}</span>")
        return None, None