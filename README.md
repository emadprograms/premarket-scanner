# Pre-Market Analyst Workbench

This Streamlit application provides a "glass box" workbench for pre-market analysis of financial assets. It allows users to run analysis in either a live or simulation mode, leveraging the Gemini API for macroeconomic insights.

## Architecture

The application is modularized to separate concerns and improve maintainability:

-   `app.py`: The entry point of the Streamlit application.
-   `modules/`: A directory containing the core application logic.
    -   `database.py`: Handles all database interactions.
    -   `gemini.py`: Manages interactions with the Gemini API, including key rotation.
    -   `processing.py`: Contains functions for data processing and technical analysis.
    -   `analysis/`: Sub-directory for AI-driven analysis engines.
        -   `macro_engine.py`: Macro context synthesis (The "Master strategist").
        -   `detail_engine.py`: Single-stock tactical deep-dives (The "Execution analyst").
    -   `ui.py`: Defines the Streamlit user interface components.
    -   `utils.py`: Provides utility functions, such as logging.
    -   `key_manager.py`: V8 Key management for multi-model rotation.
-   `tests/`: Contains comprehensive unit tests for all modules.

## Setup

1.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
2.  Create a `.streamlit/secrets.toml` file with your Turso database credentials and Gemini API keys.
3.  Run the reset DB script if you are upgrading from V4 to V5:
    ```bash
    python3 reset_db.py
    ```

## Usage

Run the Streamlit application with the following command:
```bash
streamlit run app.py
```

## Testing

To run the test suite, use `pytest`:
```bash
pytest
```

## System Documentation

For a deep dive into the system's "Glass Box" architecture, logic flow, and component breakdown, please refer to the **[System Structure Document](system_structure.md)**.
