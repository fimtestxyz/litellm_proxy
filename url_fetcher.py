"""
URL Content Fetcher and Converter for LiteLLM Proxy.

This module fetches URLs from search results and converts them to markdown
for feeding to the Ollama model.

Supports:
- HTML to Markdown conversion
- Content extraction (main content only)
- Error handling and timeout
- Content caching
"""

import os
import re
import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlparse

logger = logging.getLogger("url_fetcher")

# Try to import markdownify for HTML to Markdown conversion
try:
    from markdownify import markdownify as html_to_markdown
except ImportError:
    html_to_markdown = None

# Try to import trafilatura for better content extraction
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

# Storage directory for fetched content
CONTENT_DIR = "logs/web_search/content"

def get_content_dir() -> str:
    """Get or create the content storage directory."""
    if not os.path.exists(CONTENT_DIR):
        os.makedirs(CONTENT_DIR)
    return CONTENT_DIR


def generate_content_filename(url: str) -> str:
    """Generate a safe filename from URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace(".", "_")
    path = parsed.path.replace("/", "_").replace(".", "_")[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Sanitize to remove invalid characters
    filename = f"{domain}_{path}_{timestamp}"
    filename = re.sub(r'[^\w\-_]', '', filename)
    return filename[:100] + ".md"


def extract_domain(url: str) -> str:
    """Extract domain from URL for reference."""
    parsed = urlparse(url)
    return parsed.netloc or "unknown"


async def fetch_url_content(
    url: str,
    timeout: int = 30,
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
) -> Optional[Dict[str, Any]]:
    """
    Fetch URL and convert to markdown.
    
    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds
        user_agent: User agent string
        
    Returns:
        Dictionary with markdown content and metadata, or None if failed
    """
    try:
        logger.info(f"Fetching URL: {url}")
        
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            html_content = response.text
            content_type = response.headers.get("content-type", "text/html")
            
            # Extract content based on available tools
            markdown_content = None
            
            # Try trafilatura first (best for content extraction)
            if HAS_TRAFILATURA:
                try:
                    extracted = trafilatura.extract(
                        html_content,
                        output_format="markdown",
                        include_comments=False,
                        include_tables=True,
                        include_images=False,
                        include_links=False
                    )
                    if extracted:
                        markdown_content = extracted
                        logger.info(f"Extracted content using trafilatura")
                except Exception as e:
                    logger.warning(f"Trafilatura extraction failed: {e}")
            
            # Fallback to markdownify
            if not markdown_content and html_to_markdown:
                try:
                    # Simple HTML cleaning before conversion
                    # Remove scripts and styles
                    cleaned_html = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                    cleaned_html = re.sub(r'<style[^>]*>.*?</style>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
                    cleaned_html = re.sub(r'<header[^>]*>.*?</header>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
                    cleaned_html = re.sub(r'<footer[^>]*>.*?</footer>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
                    cleaned_html = re.sub(r'<nav[^>]*>.*?</nav>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
                    
                    markdown_content = html_to_markdown(cleaned_html)
                    logger.info(f"Converted HTML to Markdown using markdownify")
                except Exception as e:
                    logger.warning(f"Markdownify conversion failed: {e}")
            
            # Last resort: simple HTML to text
            if not markdown_content:
                try:
                    # Simple HTML tag removal
                    text = re.sub(r'<[^>]+>', ' ', html_content)
                    text = re.sub(r'\s+', ' ', text)
                    text = text.strip()
                    markdown_content = f"# Content from {extract_domain(url)}\n\n{text[:10000]}"
                    logger.info(f"Extracted text using regex")
                except Exception as e:
                    logger.warning(f"Regex extraction failed: {e}")
            
            if not markdown_content:
                logger.error(f"Failed to extract content from {url}")
                return None
            
            # Truncate if too long (keep within reasonable limits for LLM)
            if len(markdown_content) > 15000:
                markdown_content = markdown_content[:15000] + "\n\n[... content truncated ...]"
            
            return {
                "url": url,
                "domain": extract_domain(url),
                "content": markdown_content,
                "content_type": content_type,
                "fetched_at": datetime.now().isoformat(),
                "char_count": len(markdown_content)
            }
            
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching {url}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


def save_fetched_content(content_data: Dict[str, Any]) -> str:
    """
    Save fetched content to a markdown file.
    
    Args:
        content_data: Dictionary with URL and content
        
    Returns:
        Path to saved file
    """
    content_dir = get_content_dir()
    filename = generate_content_filename(content_data["url"])
    filepath = os.path.join(content_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# Source: {content_data['url']}\n")
            f.write(f"# Domain: {content_data['domain']}\n")
            f.write(f"# Fetched: {content_data['fetched_at']}\n")
            f.write(f"# Characters: {content_data['char_count']}\n")
            f.write("\n---\n\n")
            f.write(content_data["content"])
        
        logger.info(f"Saved content to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to save content: {e}")
        return ""


async def fetch_and_format_urls(
    urls: List[str],
    max_urls: int = 2,
    save_to_file: bool = True
) -> str:
    """
    Fetch multiple URLs and format as markdown context for LLM.
    
    Args:
        urls: List of URLs to fetch
        max_urls: Maximum number of URLs to process
        save_to_file: Whether to save content to files
        
    Returns:
        Formatted markdown string with content from URLs
    """
    urls_to_fetch = urls[:max_urls]
    results = []
    
    for url in urls_to_fetch:
        content_data = await fetch_url_content(url)
        
        if content_data:
            if save_to_file:
                save_fetched_content(content_data)
            results.append(content_data)
    
    if not results:
        return ""
    
    # Format as markdown context
    formatted = ["\n\n[URL CONTENT REFERENCES]\n"]
    
    for i, result in enumerate(results, 1):
        formatted.append(f"\n### Source {i}: {result['domain']}")
        formatted.append(f"**URL**: {result['url']}")
        formatted.append(f"**Fetched**: {result['fetched_at']}")
        formatted.append(f"\n{result['content']}\n")
        formatted.append("---\n")
    
    return "".join(formatted)


async def get_url_context(
    search_results: List[Dict[str, Any]],
    max_urls: int = 2
) -> str:
    """
    Get additional context by fetching URLs from search results.
    
    Args:
        search_results: List of search result dictionaries
        max_urls: Maximum URLs to fetch
        
    Returns:
        Formatted markdown context
    """
    # Extract URLs from search results
    urls = []
    for result in search_results:
        url = result.get("url")
        if url:
            urls.append(url)
    
    if not urls:
        return ""
    
    return await fetch_and_format_urls(urls, max_urls=max_urls)


# Singleton cache for fetched content
_content_cache: Dict[str, tuple[datetime, str]] = {}
CACHE_TTL = timedelta(hours=1)


def get_cached_content(url: str) -> Optional[str]:
    """Get cached content if still valid."""
    if url in _content_cache:
        timestamp, content = _content_cache[url]
        if datetime.now() - timestamp < CACHE_TTL:
            return content
        else:
            del _content_cache[url]
    return None


def cache_content(url: str, content: str):
    """Cache fetched content."""
    _content_cache[url] = (datetime.now(), content)


def clear_content_cache():
    """Clear the content cache."""
    _content_cache.clear()
    logger.info("Content cache cleared")


if __name__ == "__main__":
    # Test the module
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        # Test URL fetching
        test_urls = [
            "https://example.com",
            "https://httpbin.org/html"
        ]
        
        for url in test_urls:
            print(f"\n{'='*60}")
            print(f"Testing: {url}")
            print('='*60)
            
            result = await fetch_url_content(url)
            if result:
                print(f"Domain: {result['domain']}")
                print(f"Chars: {result['char_count']}")
                print(f"Content preview: {result['content'][:500]}...")
                
                # Save to file
                filepath = save_fetched_content(result)
                print(f"Saved to: {filepath}")
    
    asyncio.run(test())
