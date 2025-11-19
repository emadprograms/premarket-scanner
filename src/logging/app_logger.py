# src/logging/app_logger.py

import streamlit as st
from datetime import datetime, timezone
import json
import re


class AppLogger:
    """
    In-place Streamlit logger keyed by step (log_key).

    Guarantees per run (after clear()):
    - Each distinct message text is logged at most once for this logger,
      regardless of timestamp or minor whitespace differences.
    """

    MAX_LINES = 120

    def __init__(self, container, log_key: str):
        self.container = container
        self.log_key = f"logs_{log_key}"
        if self.log_key not in st.session_state:
            st.session_state[self.log_key] = []
        self._seen_key = f"seen_{log_key}"
        if self._seen_key not in st.session_state:
            st.session_state[self._seen_key] = set()

    @property
    def buffer(self) -> list[str]:
        return st.session_state[self.log_key]

    @property
    def seen(self) -> set[str]:
        return st.session_state[self._seen_key]

    def _normalize_message(self, message: str) -> str:
        """
        Normalize message for deduping:
        - strip leading/trailing spaces
        - collapse all internal whitespace to a single space
        """
        return re.sub(r"\s+", " ", message.strip())

    def _append_unique(self, raw_message: str):
        norm = self._normalize_message(raw_message)
        if norm in self.seen:
            return
        self.seen.add(norm)

        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"**{ts}Z:** {raw_message}"
        self.buffer.append(line)

        if len(self.buffer) > self.MAX_LINES:
            st.session_state[self.log_key] = self.buffer[-self.MAX_LINES:]

    def log(self, message: str):
        self._append_unique(message)
        self.display()

    def log_code(self, data, language: str = "json"):
        code_str = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
        raw_message = f"(Code Block)\n``````"
        self._append_unique(raw_message)
        self.display()

    def display(self):
        if self.container:
            with self.container:
                st.markdown("\n\n".join(self.buffer[::-1]), unsafe_allow_html=True)

    def display_logs(self):
        self.display()

    def clear(self):
        st.session_state[self.log_key] = []
        st.session_state[self._seen_key] = set()
        self.display()
