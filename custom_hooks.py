import os
import httpx
import logging
from typing import Optional, Dict, Any, List
from litellm.integrations.custom_logger import CustomLogger

# Import our modules
try:
    from ddgs_search import get_ddgs_instance, DuckDuckGoSearch
except ImportError:
    DuckDuckGoSearch = None

try:
    from temporal_parser import get_temporal_parser, TemporalParser
except ImportError:
    TemporalParser = None

try:
    from search_storage import save_search_results
except ImportError:
    def save_search_results(*args, **kwargs):
        pass  # No-op if storage not available

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_search_plugin")


class WebSearchHook(CustomLogger):
    """
    LiteLLM Custom Logger for Web Search Augmentation.
    
    Supports both DuckDuckGo (DDGS) and Tavily as search providers.
    - DDGS: Free, no API key required (default)
    - Tavily: Requires API key, more comprehensive results
    
    Also supports temporal parsing to enhance search with time-based queries.
    
    Set environment variable SEARCH_PROVIDER to choose:
    - "ddgs" or "duckduckgo" - Use DuckDuckGo (default, free)
    - "tavily" - Use Tavily (requires TAVILY_API_KEY)
    - "both" - Use both and combine results
    """
    
    def __init__(self):
        self.ddgs_client: Optional[DuckDuckGoSearch] = None
        self.temporal_parser: Optional[TemporalParser] = None
        
        # Initialize DDGS client
        if DuckDuckGoSearch:
            try:
                self.ddgs_client = get_ddgs_instance()
                logger.info("DuckDuckGo search client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize DDGS client: {e}")
        
        # Initialize temporal parser
        if TemporalParser:
            try:
                self.temporal_parser = get_temporal_parser()
                logger.info("Temporal parser initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize temporal parser: {e}")
    
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
            "weather", "temperature", "stock", "price",
            "how to", "how does", "why is", "what are",
            "list of", "top", "best", "review",
            "wikipedia", "definition", "meaning of"
        ]
        
        message_lower = message.lower()
        return any(k in message_lower for k in search_keywords)
    
    def _parse_temporal(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse temporal expression from query."""
        if not self.temporal_parser:
            return None
        
        try:
            return self.temporal_parser.parse(query)
        except Exception as e:
            logger.warning(f"Temporal parsing failed: {e}")
            return None
    
    async def _search_ddgs(self, query: str, max_results: int = 5, timelimit: Optional[str] = None, temporal_query_mod: Optional[str] = None, temporal_info: Optional[Dict] = None) -> List[Dict]:
        """Search using DuckDuckGo."""
        if not self.ddgs_client:
            logger.warning("DDGS client not available")
            return []
        
        # Modify query with temporal info if provided
        search_query = query
        if temporal_query_mod:
            search_query = f"{temporal_query_mod} {query}"
        
        try:
            results = self.ddgs_client.search(
                query=search_query,
                max_results=max_results,
                region="wt-wt",
                safesearch="moderate",
                timelimit=timelimit
            )
            
            # Save results to file
            if results:
                save_search_results(
                    query=query,
                    results=results,
                    provider="duckduckgo",
                    temporal_info=temporal_info,
                    metadata={
                        "search_query": search_query,
                        "timelimit": timelimit
                    }
                )
            
            return results
        except Exception as e:
            logger.error(f"DDGS search failed: {str(e)}")
            return []
    
    async def _search_tavily(self, query: str, max_results: int = 5, temporal_info: Optional[Dict] = None) -> List[Dict]:
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
                
                # Format results
                formatted_results = [
                    {
                        "title": r.get("title", "No Title"),
                        "url": r.get("url", ""),
                        "description": r.get("content", ""),
                        "source": "Tavily"
                    }
                    for r in results
                ]
                
                # Save results to file
                if formatted_results:
                    save_search_results(
                        query=query,
                        results=formatted_results,
                        provider="tavily",
                        temporal_info=temporal_info
                    )
                
                return formatted_results
        except Exception as e:
            logger.error(f"Tavily search failed: {str(e)}")
            return []
    
    def _format_search_results(self, results: List[Dict], source: str) -> str:
        """Format search results into a context string."""
        if not results:
            return ""
        
        formatted = [f"\n\n[{source} SEARCH RESULTS]"]
        
        # Add temporal context if available
        formatted.append("\n[/SEARCH RESULTS]\n")
        
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
        
        Detects if a search is needed, parses temporal context,
        performs the search, and injects the results into the prompt.
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
            
            # 2. Parse temporal expression
            temporal_info = self._parse_temporal(last_message)
            timelimit = None
            temporal_query_mod = None
            if temporal_info:
                logger.info(f"📅 Temporal context: {temporal_info.get('description', 'unknown')}")
                # Get timelimit parameter for DDGS
                if self.temporal_parser:
                    timelimit = self._get_timelimit(temporal_info)
                    temporal_query_mod = self.temporal_parser.format_query_modifier(temporal_info)
            
            search_provider = self._get_search_provider()
            all_results: List[Dict] = []
            
            # 3. Perform Search(es)
            if search_provider in ["ddgs", "duckduckgo", "both"]:
                ddgs_results = await self._search_ddgs(
                    last_message, 
                    max_results=5, 
                    timelimit=timelimit, 
                    temporal_query_mod=temporal_query_mod,
                    temporal_info=temporal_info
                )
                all_results.extend(ddgs_results)
                logger.info(f"DDGS found {len(ddgs_results)} results")
            
            if search_provider in ["tavily", "both"]:
                # Tavily doesn't use timelimit the same way, but we can adjust query
                tavily_results = await self._search_tavily(last_message, max_results=5, temporal_info=temporal_info)
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

            # 4. Format and Inject Context
            source_name = "DuckDuckGo" if search_provider == "ddgs" else "Web Search"
            context_text = self._format_search_results(unique_results[:5], source_name)
            
            # Build system prompt
            temporal_note = ""
            if temporal_info:
                temporal_note = f"\n[TEMPORAL CONTEXT: User is asking about '{temporal_info.get('description', 'recent period')}'.]\n"
            
            system_prompt_addition = (
                f"{temporal_note}"
                f"{context_text}"
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
    
    def _get_timelimit(self, temporal_info: Dict[str, Any]) -> Optional[str]:
        """Convert temporal info to DDGS timelimit parameter."""
        t_type = temporal_info.get("type")
        unit = temporal_info.get("unit")
        value = temporal_info.get("value", 1)
        
        # Year reference
        if t_type == "year":
            return None  # Don't use timelimit for specific years
        
        # Map units to timelimit values
        if unit == "day":
            return "d"
        elif unit == "week":
            return "w"
        elif unit == "month":
            return "m"
        elif unit == "year":
            return "y"
        
        return None


# This object is what litellm will instantiate
web_search_hook = WebSearchHook()
