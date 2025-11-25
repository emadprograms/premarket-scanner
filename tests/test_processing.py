import pandas as pd
import pytest
from unittest.mock import Mock
from src.processing import (
    get_latest_price_details,
    get_session_bars_from_db,
    calculate_vwap,
    calculate_volume_profile,
    process_session_data_to_summary,
)

def test_get_latest_price_details():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = [(150.0, '2023-01-01 10:00:00')]
    price, ts = get_latest_price_details(mock_client, 'AAPL', '2023-01-01 12:00:00', mock_logger)
    assert price == 150.0
    assert ts == '2023-01-01 10:00:00'

def test_get_session_bars_from_db():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = [
        ('2023-01-01 09:30:00', 1, 2, 3, 4, 100, 'PM'),
        ('2023-01-01 10:00:00', 5, 6, 7, 8, 200, 'RTH')
    ]
    mock_client.execute.return_value.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'session_db']
    df = get_session_bars_from_db(mock_client, 'AAPL', '2023-01-01', '2023-01-01 12:00:00', mock_logger)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2

def test_calculate_vwap():
    sample_df = pd.DataFrame({
        'High': [10, 20],
        'Low': [5, 15],
        'Close': [8, 18],
        'Volume': [100, 200]
    })
    vwap = calculate_vwap(sample_df)
    assert vwap == pytest.approx(14.33, 0.01)

def test_calculate_vwap_empty():
    vwap = calculate_vwap(pd.DataFrame())
    assert pd.isna(vwap)

def test_calculate_volume_profile():
    sample_df = pd.DataFrame({
        'High': [10, 20],
        'Low': [5, 15],
        'Close': [8, 18],
        'Volume': [100, 200]
    })
    poc = calculate_volume_profile(sample_df)
    assert poc is not None

def test_calculate_volume_profile_empty():
    poc = calculate_volume_profile(pd.DataFrame())
    assert pd.isna(poc)

def test_process_session_data_to_summary():
    mock_logger = Mock()
    sample_df = pd.DataFrame({
        'High': [10, 20],
        'Low': [5, 15],
        'Close': [8, 18],
        'Volume': [100, 200],
        'session': ['PM', 'PM']
    })
    summary = process_session_data_to_summary('AAPL', sample_df, 150.0, mock_logger)
    assert 'AAPL' in summary['summary_text']

def test_process_session_data_to_summary_empty():
    mock_logger = Mock()
    summary = process_session_data_to_summary('AAPL', pd.DataFrame(), 150.0, mock_logger)
    assert 'No Session Bars' in summary['summary_text']
