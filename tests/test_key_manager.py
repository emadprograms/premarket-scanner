from unittest.mock import Mock, patch
import pytest
from key_manager import KeyManager

@pytest.fixture
def mock_db_client():
    mock_client = Mock()
    mock_client.execute.return_value.rows = []
    mock_client.execute.return_value.columns = [
        'usage_pro', 'usage_flash_2_5', 'usage_flash_2_0', 'daily_count'
    ]
    return mock_client

@patch('key_manager.libsql_client.create_client_sync')
def test_add_key(mock_create_client, mock_db_client):
    mock_create_client.return_value = mock_db_client
    key_manager = KeyManager('db_url', 'auth_token')
    key_manager.add_key('test_key', 'test_value')
    mock_db_client.execute.assert_called()

@patch('key_manager.KeyManager._refresh_keys_from_db')
@patch('key_manager.libsql_client.create_client_sync')
def test_get_key_success(mock_create_client, mock_refresh, mock_db_client):
    mock_create_client.return_value = mock_db_client
    key_manager = KeyManager('db_url', 'auth_token')
    key_manager.available_keys.append('test_value')
    key_manager.key_to_name['test_value'] = 'test_key'
    key_manager.key_to_hash['test_value'] = 'hash'

    mock_db_client.execute.side_effect = [
        Mock(rows=[(0,)], columns=['last_used_ts']),
        Mock(rows=[(
            'hash', 0, 0, 0, '', 0, 0, 0, 0
        )], columns=[
            'key_hash', 'strikes', 'release_time', 'daily_count',
            'last_success_day', 'usage_pro', 'usage_flash_2_5',
            'usage_flash_2_0', 'last_used_ts'
        ])
    ]
    key_name, key_value, wait_time = key_manager.get_key('gemini-2.5-pro')
    assert key_name is not None
    assert key_value is not None
    assert wait_time == 0.0

@patch('key_manager.KeyManager._refresh_keys_from_db')
@patch('key_manager.libsql_client.create_client_sync')
def test_get_key_no_keys_available(mock_create_client, mock_refresh, mock_db_client):
    mock_create_client.return_value = mock_db_client
    key_manager = KeyManager('db_url', 'auth_token')
    key_name, key_value, wait_time = key_manager.get_key('gemini-2.5-pro')
    assert key_name is None
    assert key_value is None
    assert wait_time > 0

@patch('key_manager.libsql_client.create_client_sync')
def test_report_success(mock_create_client, mock_db_client):
    mock_create_client.return_value = mock_db_client
    key_manager = KeyManager('db_url', 'auth_token')
    key_manager.key_to_hash = {'test_value': 'hash'}
    mock_db_client.execute.return_value.rows = []
    mock_db_client.execute.return_value.columns = []
    key_manager.report_success('test_value', 'gemini-2.5-pro')
    mock_db_client.execute.assert_called()

@patch('key_manager.libsql_client.create_client_sync')
def test_report_failure(mock_create_client, mock_db_client):
    mock_create_client.return_value = mock_db_client
    key_manager = KeyManager('db_url', 'auth_token')
    key_manager.key_to_hash = {'test_value': 'hash'}
    mock_db_client.execute.return_value.rows = []
    mock_db_client.execute.return_value.columns = []
    key_manager.report_failure('test_value')
    mock_db_client.execute.assert_called()
