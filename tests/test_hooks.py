import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from custom_hooks import web_search_augmentation

@pytest.mark.asyncio
async def test_web_search_augmentation_triggered():
    """
    Test that the search hook is triggered for keywords and augment messages.
    """
    kwargs = {
        "messages": [
            {"role": "user", "content": "What is the latest news in 2024?"}
        ]
    }
    
    # Mocking httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"title": "AI News 2024", "content": "AI is advancing rapidly in 2024."}
        ]
    }
    mock_response.raise_for_status = lambda: None

    with patch("os.getenv", return_value="fake_tavily_key"):
        # We need to mock the async context manager and the post method
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await web_search_augmentation(kwargs)
            
            # Check if messages were augmented
            assert len(result["messages"]) == 2
            assert result["messages"][0]["role"] == "system"
            assert "[WEB SEARCH CONTEXT]" in result["messages"][0]["content"]
            assert "AI News 2024" in result["messages"][0]["content"]

@pytest.mark.asyncio
async def test_web_search_not_triggered():
    """
    Test that the search hook is NOT triggered for normal queries.
    """
    kwargs = {
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ]
    }
    
    # We expect the function to return kwargs unchanged (or at least without augmentation)
    result = await web_search_augmentation(kwargs)
    
    # Check that it remains 1 message
    assert len(result["messages"]) == 1
    assert result["messages"][0]["content"] == "Hello, how are you?"

@pytest.mark.asyncio
async def test_web_search_fail_silently():
    """
    Test that the proxy remains resilient even if search fails.
    """
    kwargs = {
        "messages": [
            {"role": "user", "content": "Search for AI news."}
        ]
    }
    
    with patch("os.getenv", return_value="fake_tavily_key"):
        with patch("httpx.AsyncClient.post", side_effect=Exception("API Down")):
            result = await web_search_augmentation(kwargs)
            
            # Should fail silently and return original messages
            assert len(result["messages"]) == 1
            assert "Search for AI news." in result["messages"][0]["content"]
