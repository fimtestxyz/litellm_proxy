import pytest
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock
from custom_hooks import web_search_hook
from routing_hook import smart_router_hook

@pytest.mark.asyncio
async def test_web_search_hook_triggered():
    """
    Test that the search hook is triggered for keywords and augment messages.
    """
    kwargs = {
        "data": {
            "messages": [
                {"role": "user", "content": "What is the latest news in 2024?"}
            ]
        }
    }
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"title": "AI News 2024", "url": "https://example.com", "content": "AI is advancing rapidly in 2024."}
        ]
    }
    mock_response.raise_for_status = lambda: None

    env_vars = {
        "TAVILY_API_KEY": "fake_tavily_key",
        "SEARCH_PROVIDER": "tavily",
        "ENABLE_URL_FETCH": "false"
    }

    with patch("os.getenv", side_effect=lambda k, d=None: env_vars.get(k, d)):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            result_data = await web_search_hook.async_pre_call_hook(**kwargs)
            
            assert len(result_data["messages"]) >= 2
            assert any(m["role"] == "system" for m in result_data["messages"])
            system_msg = next(m for m in result_data["messages"] if m["role"] == "system")
            assert "[Web Search SEARCH RESULTS]" in system_msg["content"]
            assert "AI News 2024" in system_msg["content"]

@pytest.mark.asyncio
async def test_smart_router_coding():
    """
    Test that 'smart-proxy' routes to the correct Ollama coding model.
    """
    kwargs = {
        "data": {
            "model": "smart-proxy",
            "messages": [
                {"role": "user", "content": "Write a python function to sort a list."}
            ]
        },
        "litellm_call_id": "test_coding"
    }
    
    result_data = await smart_router_hook.async_pre_call_hook(**kwargs)
    
    # Check that it mapped 'coding' to the actual Ollama model string
    assert result_data["model"] == "ollama/qwen2.5-coder:14b"
    
    # Verify log file was created
    log_files = os.listdir("logs/routing")
    assert any("test_coding" in f for f in log_files)

@pytest.mark.asyncio
async def test_smart_router_reasoning():
    """
    Test that 'smart-proxy' routes to the correct Ollama reasoning model.
    """
    kwargs = {
        "data": {
            "model": "smart-proxy",
            "messages": [
                {"role": "user", "content": "Think step by step about the implications of AGI."}
            ]
        }
    }
    
    result_data = await smart_router_hook.async_pre_call_hook(**kwargs)
    
    assert result_data["model"] == "ollama/llama3:70b"

@pytest.mark.asyncio
async def test_smart_router_summary():
    """
    Test that 'smart-proxy' routes to the correct Ollama summary model.
    """
    kwargs = {
        "data": {
            "model": "smart-proxy",
            "messages": [
                {"role": "user", "content": "Summarize this article."}
            ]
        }
    }
    
    result_data = await smart_router_hook.async_pre_call_hook(**kwargs)
    
    assert result_data["model"] == "ollama/qwen2-vl"

@pytest.mark.asyncio
async def test_smart_router_default():
    """
    Test that 'smart-proxy' routes to 'fast' model by default.
    """
    kwargs = {
        "data": {
            "model": "smart-proxy",
            "messages": [
                {"role": "user", "content": "What's the capital of Japan?"}
            ]
        }
    }
    
    result_data = await smart_router_hook.async_pre_call_hook(**kwargs)
    
    assert result_data["model"] == "ollama/qwen2.5:3b"

@pytest.mark.asyncio
async def test_smart_router_skip_other_models():
    """
    Test that the router does not affect other models.
    """
    kwargs = {
        "data": {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Write code."}
            ]
        }
    }
    
    result_data = await smart_router_hook.async_pre_call_hook(**kwargs)
    
    assert result_data["model"] == "gpt-4"
