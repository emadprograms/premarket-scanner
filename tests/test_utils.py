from unittest.mock import Mock
from src.utils import AppLogger

def test_log():
    mock_container = Mock()
    logger = AppLogger(mock_container)
    logger.log("Test message")
    assert len(logger.log_messages) == 1
    assert "Test message" in logger.log_messages[0]
    mock_container.markdown.assert_called_once()

def test_log_code():
    mock_container = Mock()
    logger = AppLogger(mock_container)
    logger.log_code("{'key': 'value'}", language='json')
    assert len(logger.log_messages) == 1
    assert "(See code block below)" in logger.log_messages[0]
    mock_container.markdown.assert_called_once()
    mock_container.code.assert_called_once_with("{'key': 'value'}", language='json')

def test_log_code_json():
    mock_container = Mock()
    logger = AppLogger(mock_container)
    logger.log_code({'key': 'value'}, language='json')
    assert len(logger.log_messages) == 1
    assert "(See code block below)" in logger.log_messages[0]
    mock_container.markdown.assert_called_once()
    mock_container.json.assert_called_once_with({'key': 'value'})

def test_flush():
    mock_container = Mock()
    logger = AppLogger(mock_container)
    logger.log("Message 1")
    logger.log("Message 2")
    logger.flush()
    assert mock_container.markdown.call_count == 3  # 2 logs + 1 flush
