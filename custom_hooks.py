import os
import httpx
import logging
from typing import Optional, Dict, Any, List
from litellm.integrations.custom_logger import CustomLogger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_search_plugin")

class WebSearchHook(CustomLogger):
    """
    LiteLLM Custom Logger for Web Search Augmentation.
    """
    async def async_pre_call_hook(
        self,
        **kwargs
    ):
        # In this version of LiteLLM Proxy, 'data' contains the request body
        request_data = kwargs.get("data", {})
        messages = request_data.get("messages", [])
        
        try:
            if not messages:
                return request_data

            last_message = messages[-1].get("content", "")
            if not isinstance(last_message, str):
                return request_data

            # 1. Intent Detection
            search_keywords = ["search", "latest", "news", "current", "2024", "2025", "today"]
            if not any(k in last_message.lower() for k in search_keywords):
                return request_data

            logger.info(f"Triggering web search for query: {last_message}")

            # 2. Perform Search (Async)
            tavily_api_key = os.getenv("TAVILY_API_KEY")
            if not tavily_api_key:
                logger.warning("TAVILY_API_KEY not set. Skipping search.")
                return request_data

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "query": last_message,
                        "api_key": tavily_api_key,
                        "search_depth": "basic",
                        "max_results": 3
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                results = response.json()

                # 3. Format Context
                search_results = results.get("results", [])
                if not search_results:
                    return request_data

                context_text = "\n".join([
                    f"- {r.get('title', 'No Title')}: {r.get('content', 'No Content')}"
                    for r in search_results
                ])

                # 4. Inject Context
                system_prompt_addition = (
                    f"\n\n[WEB SEARCH CONTEXT]\n{context_text}\n[/WEB SEARCH CONTEXT]\n"
                    "Use the provided context to answer the user query accurately."
                )

                # Check for existing system message
                if messages and messages[0].get("role") == "system":
                    messages[0]["content"] += system_prompt_addition
                else:
                    messages.insert(0, {"role": "system", "content": system_prompt_addition})

                # Update request_data's messages
                request_data["messages"] = messages
                logger.info("Successfully injected search context into prompt.")

        except Exception as e:
            logger.error(f"Web search plugin failed: {str(e)}")

        return request_data

# This object is what litellm will instantiate
web_search_hook = WebSearchHook()
