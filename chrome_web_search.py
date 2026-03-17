"""
Chrome Web Search Module for LiteLLM Proxy using Playwright (CDP).

This module uses Playwright to interact with a local Chrome/Chromium browser
via Chrome DevTools Protocol (CDP), enabling search result extraction
while maintaining a local profile for persistence.

Features:
- Playwright-based CDP interaction
- Local Chrome profile management
- Google search with proper query parameters
- Stealth measures to avoid detection
- Extracts: title, url, description
- Supports pagination/multiple pages
"""

import os
import asyncio
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

# Try to import playwright
try:
    from playwright.async_api import async_playwright, BrowserContext, Page
    import playwright_stealth
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logging.warning("Playwright or playwright-stealth not installed. Chrome search will not work.")

logger = logging.getLogger("chrome_web_search")

# Chrome profile directory
CHROME_PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chrome_profile")
CHROME_DATA_DIR = os.path.join(CHROME_PROFILE_DIR, "data")

class ChromeSearchConfig:
    """Configuration for Chrome web search using Playwright."""
    
    def __init__(
        self,
        headless: bool = True,
        user_agent: Optional[str] = None,
        profile_dir: str = CHROME_DATA_DIR,
        timeout: int = 30,
        num_results: int = 10,
        binary_location: Optional[str] = None
    ):
        self.headless = headless
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        self.profile_dir = profile_dir
        self.timeout = timeout
        self.num_results = num_results
        self.binary_location = binary_location
        
        # Ensure profile directory exists
        os.makedirs(profile_dir, exist_ok=True)

async def extract_search_results(page: Page, num_results: int = 10) -> List[Dict[str, str]]:
    """
    Extract search results from the current page using JavaScript.
    """
    try:
        # Wait for search results container
        await page.wait_for_selector("#search", timeout=5000)
    except Exception:
        pass

    results = await page.evaluate("""
        () => {
            const results = [];
            const seenUrls = new Set();
            
            // Google search result containers often use these classes or attributes
            const containers = document.querySelectorAll('div.g, div.MjjYud, div.N54PNb, div.tF2Cxc, div.srk7f, div[data-hveid]');
            
            containers.forEach(container => {
                // Find the main link
                const link = container.querySelector('a[href^="http"]');
                if (!link) return;
                
                const href = link.href;
                if (!href || !href.startsWith('http') || seenUrls.has(href)) return;
                
                // Skip Google-internal links
                if (href.includes('google.com') || href.includes('accounts.google') || 
                    href.includes('support.google') || href.includes('policies.google') ||
                    href.includes('webhp')) {
                    if (!href.includes('youtube.com') && !href.includes('blog.youtube.com')) return;
                }
                
                // Extract title - usually in h3
                let title = '';
                const heading = container.querySelector('h3, [role=\"heading\"]');
                if (heading) title = heading.textContent.trim();
                if (!title) title = link.textContent.trim();
                
                if (!title || title.length < 3) return;
                
                // Extract description
                let desc = '';
                const descSelectors = [
                    '.VwiC3b',          // Primary snippet class
                    '.MUwYV',           // Snippet variation
                    '.yXK7lf',          // Snippet container
                    'div[data-sncf=\"1\"]', // Container often holding snippet
                    'div[data-sncf=\"2\"]', // Alternative snippet container
                    '.kb0PBd',          // General content block
                    '.st'               // Legacy snippet class
                ];
                
                for (const sel of descSelectors) {
                    const el = container.querySelector(sel);
                    if (el) {
                        const text = el.textContent.trim();
                        if (text.length > 10) {
                            desc = text;
                            break;
                        }
                    }
                }
                
                // If no specific description found, look for any span or div with significant text
                if (!desc) {
                    const spans = container.querySelectorAll('span, div');
                    for (const s of spans) {
                        const text = s.textContent.trim();
                        if (text.length > 50 && text.length < 500 && !text.includes(title)) {
                            desc = text;
                            break;
                        }
                    }
                }
                
                seenUrls.add(href);
                results.push({
                    title: title.substring(0, 200),
                    url: href,
                    description: desc.substring(0, 500)
                });
            });
            
            return results;
        }
    """)
    
    return results[:num_results]

def build_google_url(query: str, num: int = 10, start: int = 0) -> str:
    """Build Google search URL."""
    encoded_query = query.replace(" ", "+")
    return f"https://www.google.com/search?q={encoded_query}&num={num}&start={start}&hl=en"

async def search_with_chrome(
    query: str,
    num_results: int = 10,
    headless: bool = True,
    profile_dir: str = CHROME_DATA_DIR,
    binary_location: Optional[str] = None,
    scrape_extra_pages: bool = True
) -> List[Dict[str, str]]:
    """
    Perform Google search using Playwright and return results.
    """
    if not HAS_PLAYWRIGHT:
        logger.error("Playwright is not installed")
        return []

    config = ChromeSearchConfig(
        headless=headless,
        profile_dir=profile_dir,
        num_results=num_results,
        binary_location=binary_location
    )

    # Clean up lock files
    lock_file = os.path.join(config.profile_dir, "SingletonLock")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except:
            pass

    all_results = []
    seen_urls = set()

    async with async_playwright() as p:
        try:
            launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir=config.profile_dir,
                headless=config.headless,
                executable_path=config.binary_location,
                args=launch_args,
                user_agent=config.user_agent,
                viewport={'width': 1920, 'height': 1080}
            )

            page = context.pages[0] if context.pages else await context.new_page()
            await playwright_stealth.Stealth().apply_stealth_async(page)
            
            # Pages to scrape (Page 1: start=0, Page 2: start=10, etc.)
            # User specifically mentioned "start=1 more page", which often means second page results.
            # We'll scrape Page 1 and Page 2 to be thorough.
            pages_to_scrape = [0]
            if scrape_extra_pages:
                pages_to_scrape.append(10) # Next page starts at 10 if num=10
            
            for start_index in pages_to_scrape:
                url = build_google_url(query, num=num_results, start=start_index)
                logger.info(f"Searching Google (start={start_index}): {query}")
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=config.timeout * 1000)
                    await asyncio.sleep(2) # Allow results to settle
                    
                    content = await page.content()
                    if "captcha" in content.lower() or "unusual traffic" in content.lower():
                        logger.warning(f"Google blocked the request at start={start_index}")
                        break

                    page_results = await extract_search_results(page, num_results)
                    for r in page_results:
                        if r['url'] not in seen_urls:
                            seen_urls.add(r['url'])
                            all_results.append(r)
                            
                    if len(all_results) >= num_results * len(pages_to_scrape):
                        break
                except Exception as e:
                    logger.error(f"Failed to scrape page at start={start_index}: {e}")
                    continue

            logger.info(f"Total results found: {len(all_results)}")
            await context.close()
            
        except Exception as e:
            logger.error(f"Playwright search failed: {e}")
            
    return all_results[:num_results * 2] # Return up to 2 pages worth of results

def search_sync(
    query: str,
    num_results: int = 10,
    headless: bool = True,
    profile_dir: str = CHROME_DATA_DIR,
    binary_location: Optional[str] = None
) -> List[Dict[str, str]]:
    """Synchronous wrapper."""
    return asyncio.run(search_with_chrome(
        query, num_results, headless, profile_dir, binary_location
    ))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "Claude AI news"
    results = search_sync(query, num_results=10)
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r['title']}\n   {r['url']}\n   {r['description'][:200]}...")
