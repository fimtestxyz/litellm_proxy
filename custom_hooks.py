import os
import httpx
import logging
from typing import Optional, Dict, Any, List
from litellm.integrations.custom_logger import CustomLogger

# Import our DDGS module
try:
    from ddgs_search import get_ddgs_instance, DuckDuckGoSearch
except ImportError:
    DuckDuckGoSearch = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_search_plugin")


class WebSearchHook(CustomLogger):
    """
    LiteLLM Custom Logger for Web Search Augmentation.
    
    Supports both DuckDuckGo (DDGS) and Tavily as search providers.
    - DDGS: Free, no API key required (default)
    - Tavily: Requires API key, more comprehensive results
    
    Set environment variable SEARCH_PROVIDER to choose:
    - "ddgs" or "duckduckgo" - Use DuckDuckGo (default, free)
    - "tavily" - Use Tavily (requires TAVILY_API_KEY)
    - "both" - Use both and combine results
    """
    
    def __init__(self):
        self.ddgs_client: Optional[DuckDuckGoSearch] = None
        if DuckDuckGoSearch:
            try:
                self.ddgs_client = get_ddgs_instance()
                logger.info("DuckDuckGo search client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize DDGS client: {e}")
    
    def _get_search_provider(self) -> str:
        """Get the configured search provider."""
        return os.getenv("SEARCH_PROVIDER", "ddgs").lower()
    
    def _detect_search_intent(self, message: str) -> bool:
        """
        Detect if the message warrants a web search.
        
        Checks for common search trigger keywords.
        """
        search_keywords = [
            "search", "find", "look up", "what is", "who is", "when did",
            "latest", "news", "current", "today", "yesterday",
            "2024", "2025", "2026",  # Years - likely want current info
            "weather", "temperature", "stock", "price",
            "how to", "how does", "why is", "what are",
            "list of", "top", "best", "review",
            "wikipedia", "definition", "meaning of"
        ]
        
        message_lower = message.lower()
        return any(k in message_lower for k in search_keywords)
    
    async def _search_ddgs(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search using DuckDuckGo."""
        if not self.ddgs_client:
            logger.warning("DDGS client not available")
            return []
        
        try:
            results = self.ddgs_client.search(
                query=query,
                max_results=max_results,
                region="wt-wt",
                safesearch="moderate"
            )
            return results
        except Exception as e:
            logger.error(f"DDGS search failed: {str(e)}")
            return []
    
    async def _search_tavily(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search using Tavily API."""
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            logger.warning("TAVILY_API_KEY not set")
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "query": query,
                        "api_key": tavily_api_key,
                        "search_depth": "basic",
                        "max_results": max_results
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                results = data.get("results", [])
                return [
                    {
                        "title": r.get("title", "No Title"),
                        "url": r.get("url", ""),
                        "description": r.get("content", ""),
                        "source": "Tavily"
                    }
                    for r in results
                ]
        except Exception as e:
            logger.error(f"Tavily search failed: {str(e)}")
            return []
    
    def _format_search_results(self, results: List[Dict], source: str) -> str:
        """Format search results into a context string."""
        if not results:
            return ""
        
        formatted = [f"\n\n[{source} SEARCH RESULTS]"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No Title")
            url = r.get("url", "")
            desc = r.get("description", "")
            
            formatted.append(f"\n{i}. {title}")
            if url:
                formatted.append(f"   URL: {url}")
            if desc:
                # Truncate long descriptions
                desc = desc[:300] + "..." if len(desc) > 300 else desc
                formatted.append(f"   {desc}")
        
        formatted.append("\n[/SEARCH RESULTS]\n")
        return "".join(formatted)
    
    async def async_pre_call_hook(
        self,
        **kwargs
    ):
        """
        LiteLLM hook that runs before each model call.
        
        Detects if a search is needed, performs the search,
        and injects the results into the prompt.
        """
        request_data = kwargs.get("data", {})
        messages = request_data.get("messages", [])
        
        try:
            if not messages:
                return request_data

            last_message = messages[-1].get("content", "")
            if not isinstance(last_message, str):
                return request_data

            # 1. Intent Detection - Should we search?
            if not self._detect_search_intent(last_message):
                return request_data
            
            # Check if search is explicitly disabled
            if os.getenv("DISABLE_WEB_SEARCH", "false").lower() == "true":
                return request_data

            logger.info(f"🔍 Web search triggered for: {last_message[:100]}...")
            
            search_provider = self._get_search_provider()
            all_results: List[Dict] = []
            
            # 2. Perform Search(es)
            if search_provider in ["ddgs", "duckduckgo", "both"]:
                ddgs_results = await self._search_ddgs(last_message, max_results=5)
                all_results.extend(ddgs_results)
                logger.info(f"DDGS found {len(ddgs_results)} results")
            
            if search_provider in ["tavily", "both"]:
                tavily_results = await self._search_tavily(last_message, max_results=5)
                all_results.extend(tavily_results)
                logger.info(f"Tavily found {len(tavily_results)} results")
            
            # Deduplicate results based on URL
            seen_urls = set()
            unique_results = []
            for r in all_results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(r)
            
            if not unique_results:
                logger.warning("No search results found")
                return request_data

            # 3. Format and Inject Context
            source_name = "DuckDuckGo" if search_provider == "ddgs" else "Web Search"
            context_text = self._format_search_results(unique_results[:5], source_name)
            
            system_prompt_addition = (
                f"\n{context_text}"
                "Use the above search results to provide accurate, up-to-date information. "
                "Cite the sources when possible. If the search results don't contain "
                "relevant information, you may still answer based on your knowledge "
                "but note that the information may be outdated."
            )

            # Inject into messages
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] += system_prompt_addition
            else:
                messages.insert(0, {
                    "role": "system", 
                    "content": "You are a helpful assistant with access to web search." + system_prompt_addition
                })

            request_data["messages"] = messages
            logger.info(f"✅ Successfully injected {len(unique_results)} search results into prompt")

        except Exception as e:
            logger.error(f"Web search hook error: {str(e)}")

        return request_data


# This object is what litellm will instantiate
web_search_hook = WebSearchHook()
