from unittest.mock import Mock, patch
from src.gemini import initialize_key_manager, call_gemini_with_rotation

@patch('src.gemini.KeyManager')
def test_initialize_key_manager(mock_key_manager):
    km_instance = Mock()
    mock_key_manager.return_value = km_instance
    km = initialize_key_manager('db_url', 'auth_token')
    assert km == km_instance

@patch('src.gemini.requests.post')
@patch('src.gemini.KEY_MANAGER_INSTANCE')
def test_call_gemini_with_rotation_success(mock_km_instance, mock_post):
    mock_logger = Mock()
    mock_km_instance.get_key.return_value = ('key_name', 'api_key', 0)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'candidates': [{'content': {'parts': [{'text': 'response'}]}}]
    }
    mock_post.return_value = mock_response

    response, error = call_gemini_with_rotation(
        'prompt', 'system_prompt', mock_logger, 'gemini-2.5-pro'
    )
    assert response == 'response'
    assert error is None
    mock_km_instance.report_success.assert_called_once()

@patch('src.gemini.requests.post')
@patch('src.gemini.KEY_MANAGER_INSTANCE')
def test_call_gemini_with_rotation_failure(mock_km_instance, mock_post):
    mock_logger = Mock()
    mock_km_instance.get_key.return_value = ('key_name', 'api_key', 0)
    mock_response = Mock()
    mock_response.status_code = 500
    mock_post.return_value = mock_response

    response, error = call_gemini_with_rotation(
        'prompt', 'system_prompt', mock_logger, 'gemini-2.5-pro', max_retries=1
    )
    assert response is None
    assert error is not None
    mock_km_instance.report_failure.assert_called_once()

@patch('src.gemini.requests.post')
@patch('src.gemini.KEY_MANAGER_INSTANCE')
def test_call_gemini_with_rotation_rate_limit(mock_km_instance, mock_post):
    mock_logger = Mock()
    mock_km_instance.get_key.return_value = ('key_name', 'api_key', 0)
    mock_response = Mock()
    mock_response.status_code = 429
    mock_post.return_value = mock_response

    response, error = call_gemini_with_rotation(
        'prompt', 'system_prompt', mock_logger, 'gemini-2.5-pro', max_retries=1
    )
    assert response is None
    assert error is not None
    mock_km_instance.report_failure.assert_called_once()
