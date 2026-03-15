"""
DuckDuckGo Search Module for LiteLLM Proxy.

This module provides web search functionality using DuckDuckGo's DDGS API.
It can be used as an alternative or alongside Tavily search.

Usage:
    from ddgs import DDGS
    
    ddgs = DDGS()
    results = ddgs.text("latest AI news", max_results=5)
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        raise ImportError("Please install ddgs: pip install ddgs")

logger = logging.getLogger("ddgs_search")

class DuckDuckGoSearch:
    """
    Wrapper for DuckDuckGo search with caching and error handling.
    """
    
    def __init__(self, cache_ttl: int = 300):
        """
        Initialize DuckDuckGo Search.
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default: 5 minutes)
        """
        self.ddgs = DDGS()
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[List[Dict], datetime]] = {}
    
    def _get_cache(self, query: str) -> Optional[List[Dict]]:
        """Get cached results if still valid."""
        if query in self._cache:
            results, timestamp = self._cache[query]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return results
            else:
                del self._cache[query]
        return None
    
    def _set_cache(self, query: str, results: List[Dict]):
        """Cache search results."""
        self._cache[query] = (results, datetime.now())
    
    def search(
        self, 
        query: str, 
        max_results: int = 5,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        cache: bool = True
    ) -> List[Dict]:
        """
        Perform a web search using DuckDuckGo.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return (default: 5)
            region: Search region (default: "wt-wt" for worldwide)
            safesearch: Safe search level: "on", "moderate", "off" (default: "moderate")
            timelimit: Time limit for results (e.g., "d" for day, "w" for week, "m" for month, "y" for year)
            cache: Whether to use caching (default: True)
            
        Returns:
            List of dictionaries containing search results with keys:
                - title: Result title
                - url: Result URL
                - description: Result snippet/description
                - source: Always "DuckDuckGo"
        """
        # Check cache first
        if cache:
            cached = self._get_cache(query)
            if cached:
                logger.info(f"Returning cached results for: {query}")
                return cached[:max_results]
        
        try:
            logger.info(f"Searching DuckDuckGo for: {query}")
            
            results = []
            for r in self.ddgs.text(
                query, 
                max_results=max_results,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit
            ):
                results.append({
                    "title": r.get("title", "No Title"),
                    "url": r.get("href", r.get("url", "")),
                    "description": r.get("body", r.get("desc", "")),
                    "source": "DuckDuckGo"
                })
            
            # Cache the results
            if cache:
                self._set_cache(query, results)
            
            logger.info(f"Found {len(results)} results for: {query}")
            return results
            
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {str(e)}")
            return []
    
    def search_news(
        self, 
        query: str, 
        max_results: int = 5,
        region: str = "wt-wt",
        timelimit: str = "w"
    ) -> List[Dict]:
        """
        Search for news articles using DuckDuckGo.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            region: Search region
            timelimit: Time limit (d, w, m, y)
            
        Returns:
            List of news article dictionaries
        """
        try:
            logger.info(f"Searching DuckDuckGo news for: {query}")
            
            results = []
            for r in self.ddgs.news(
                query, 
                max_results=max_results,
                region=region,
                timelimit=timelimit
            ):
                results.append({
                    "title": r.get("title", "No Title"),
                    "url": r.get("url", ""),
                    "description": r.get("body", ""),
                    "source": r.get("source", "DuckDuckGo"),
                    "date": r.get("date", ""),
                    "image": r.get("image", "")
                })
            
            return results
            
        except Exception as e:
            logger.error(f"DuckDuckGo news search failed: {str(e)}")
            return []
    
    def clear_cache(self):
        """Clear the search cache."""
        self._cache.clear()
        logger.info("Search cache cleared")


# Singleton instance
_ddgs_instance: Optional[DuckDuckGoSearch] = None

def get_ddgs_instance() -> DuckDuckGoSearch:
    """Get or create the singleton DDGS instance."""
    global _ddgs_instance
    if _ddgs_instance is None:
        _ddgs_instance = DuckDuckGoSearch()
    return _ddgs_instance


def search_web(
    query: str, 
    max_results: int = 5,
    region: str = "wt-wt",
    safesearch: str = "moderate"
) -> List[Dict]:
    """
    Convenience function to perform a web search.
    
    Args:
        query: Search query
        max_results: Maximum results
        region: Search region
        safesearch: Safe search level
        
    Returns:
        List of search results
    """
    ddgs = get_ddgs_instance()
    return ddgs.search(query, max_results, region, safesearch)


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)
    
    results = search_web("latest AI news 2025", max_results=3)
    for r in results:
        print(f"\n📰 {r['title']}")
        print(f"   {r['description'][:100]}...")
        print(f"   🔗 {r['url']}")
