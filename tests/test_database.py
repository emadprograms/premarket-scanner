from unittest.mock import Mock, patch
from src.database import (
    get_db_connection,
    init_db_schema,
    get_latest_economy_card_date,
    get_eod_economy_card,
    get_eod_card_data_for_screener,
    get_all_tickers_from_db,
    save_snapshot,
)

@patch('src.database.st')
@patch('src.database.create_client_sync')
def test_get_db_connection(mock_create_client, mock_st):
    mock_client = Mock()
    mock_create_client.return_value = mock_client
    mock_st.secrets.get.return_value = {"db_url": "test_url", "auth_token": "test_token"}
    with patch('src.database.TURSO_DB_URL_HTTPS', 'test_url'), \
         patch('src.database.TURSO_AUTH_TOKEN', 'test_token'):
        conn = get_db_connection()
        assert conn == mock_client

def test_init_db_schema():
    mock_client = Mock()
    mock_logger = Mock()
    init_db_schema(mock_client, mock_logger)
    mock_client.execute.assert_called_once()

def test_get_latest_economy_card_date():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = [('2023-01-01',)]
    date = get_latest_economy_card_date(mock_client, '2023-01-02 10:00:00', mock_logger)
    assert date == '2023-01-01'

def test_get_latest_economy_card_date_empty():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = []
    date = get_latest_economy_card_date(mock_client, '2023-01-02 10:00:00', mock_logger)
    assert date is None

def test_get_eod_economy_card():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = [('{"key": "value"}',)]
    card = get_eod_economy_card(mock_client, '2023-01-01', mock_logger)
    assert card == {'key': 'value'}

def test_get_eod_economy_card_empty():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = []
    card = get_eod_economy_card(mock_client, '2023-01-01', mock_logger)
    assert card is None

def test_get_eod_card_data_for_screener():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = [('AAPL', '{"screener_briefing": "Buy"}')]
    mock_client.execute.return_value.columns = ['ticker', 'company_card_json']
    data = get_eod_card_data_for_screener(mock_client, ['AAPL'], '2023-01-01', mock_logger)
    assert 'AAPL' in data

def test_get_all_tickers_from_db():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = [('AAPL',), ('GOOG',)]
    tickers = get_all_tickers_from_db(mock_client, mock_logger)
    assert tickers == ['AAPL', 'GOOG']

def test_get_all_tickers_from_db_empty():
    mock_client = Mock()
    mock_logger = Mock()
    mock_client.execute.return_value.rows = []
    tickers = get_all_tickers_from_db(mock_client, mock_logger)
    assert tickers == []

def test_save_snapshot():
    mock_client = Mock()
    mock_logger = Mock()
    save_snapshot(mock_client, 'news', {}, 'stats', 'briefing', mock_logger)
    mock_client.execute.assert_called_once()
