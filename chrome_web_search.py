import os
import asyncio
import logging
import random
import json
import time
from typing import List, Dict, Optional

try:
    from playwright.async_api import async_playwright, Page, BrowserContext, Browser
    # import playwright_stealth
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logging.warning("Playwright or playwright-stealth not installed.")

logger = logging.getLogger("chrome_web_search")

# Project directories
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROME_PROFILE_DIR = os.path.join(PROJECT_DIR, ".chrome_profile")
CHROME_DATA_DIR = os.path.join(CHROME_PROFILE_DIR, "data")
PROFILES_DIR = os.path.join(PROJECT_DIR, "chrome-profiles")
PIDS_DIR = os.path.join(PROJECT_DIR, ".pids")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

class ChromeSearchConfig:
    def __init__(
        self,
        headless: bool = False,
        profile_dir: str = CHROME_DATA_DIR,
        timeout: int = 30,
        num_results: int = 10,
        binary_location: Optional[str] = None,
        cdp_url: Optional[str] = None
    ):
        self.headless = headless
        self.profile_dir = profile_dir
        self.timeout = timeout
        self.num_results = num_results
        self.cdp_url = cdp_url or os.getenv("CHROME_CDP_URL")
        
        mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if not binary_location and os.path.exists(mac_chrome):
            self.binary_location = mac_chrome
        else:
            self.binary_location = binary_location
            
        os.makedirs(profile_dir, exist_ok=True)

def build_google_url(query: str, num: int = 10) -> str:
    encoded_query = query.replace(" ", "+")
    return f"https://www.google.com/search?q={encoded_query}&num={num}&hl=en"

async def get_running_profile_cdp() -> Optional[str]:
    """Check if any profile managed by chrome-profile-manager.sh is running."""
    if not os.path.exists(PIDS_DIR) or not os.path.exists(PROFILES_DIR):
        return None
    
    for pid_file in os.listdir(PIDS_DIR):
        if pid_file.endswith(".pid"):
            profile_name = pid_file[:-4]
            pid_path = os.path.join(PIDS_DIR, pid_file)
            try:
                with open(pid_path, "r") as f:
                    pid = int(f.read().strip())
                
                # Check if process is running (Unix specific)
                try:
                    os.kill(pid, 0)
                except OSError:
                    continue # Process not running
                
                # Read config for port
                config_path = os.path.join(PROFILES_DIR, profile_name, "config.json")
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        port = config.get("port")
                        if port:
                            return f"http://localhost:{port}"
            except Exception as e:
                logger.debug(f"Error checking profile {profile_name}: {e}")
                continue
    return None

async def extract_search_results(page: Page, num_results: int = 10) -> List[Dict[str, str]]:
    """Extract search results with multiple selector fallbacks."""
    try:
        # Wait for search results to appear, with a reasonable timeout
        await page.wait_for_selector("#search, .g, div[data-hveid]", timeout=10000)
    except Exception:
        logger.warning("Timeout waiting for search results selector")

    return await page.evaluate(f"""
        (maxResults) => {{
            const results = [];
            // Common Google Search Result Selectors
            const containerSelectors = [
                'div.g', 
                'div.MjjYud', 
                'div.tF2Cxc', 
                'div[data-hveid]', 
                '.WwS6pf',
                'div.SrG6Fe'
            ];
            
            let containers = [];
            for (const sel of containerSelectors) {{
                const found = document.querySelectorAll(sel);
                if (found.length >= 2) {{
                    containers = found;
                    break;
                }}
            }}
            
            if (containers.length === 0) {{
                // Fallback: try all div.g
                containers = document.querySelectorAll('div.g');
            }}
            
            containers.forEach(container => {{
                if (results.length >= maxResults) return;

                const link = container.querySelector('a[href^="http"]');
                if (!link) return;
                
                const href = link.href;
                // Filter out internal Google links
                if (href.includes('google.com/search') || 
                    href.includes('google.com/url?q=') ||
                    href.includes('google.com/preferences')) return;
                
                const titleEl = container.querySelector('h3, [role="heading"], .vv778b');
                const title = titleEl ? titleEl.textContent.trim() : "";
                
                // Try multiple snippet selectors
                const snippetSelectors = [
                    'div[data-sncf]', 
                    '.VwiC3b', 
                    '.MUwYV', 
                    '.yXK7lf', 
                    '.st',
                    'div.kb0u9b',
                    '.Z26q7c'
                ];
                
                let snippet = "";
                for (const sSel of snippetSelectors) {{
                    const sEl = container.querySelector(sSel);
                    if (sEl) {{
                        snippet = sEl.textContent.trim();
                        if (snippet) break;
                    }}
                }}
                
                if (title && href && title.length > 2) {{
                    // Avoid duplicates
                    if (!results.some(r => r.url === href)) {{
                        results.push({{
                            title: title.substring(0, 250),
                            url: href,
                            description: snippet.substring(0, 700)
                        }});
                    }}
                }}
            }});
            return results;
        }}
    """, num_results)

async def human_like_scroll(page: Page):
    """Perform a human-like scroll action."""
    try:
        for _ in range(random.randint(1, 3)):
            scroll_amount = random.randint(200, 600)
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await asyncio.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass

async def search_with_chrome(
    query: str,
    num_results: int = 10,
    headless: bool = False,
    profile_dir: str = CHROME_DATA_DIR,
    binary_location: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Search using Chrome with profile and stealth.
    Priority:
    1. Connect to existing running profile via CDP.
    2. Launch a persistent context with stealth.
    """
    if not HAS_PLAYWRIGHT:
        logger.error("Playwright not installed. Search failed.")
        return []

    # Check for running profiles first (stealthiest)
    cdp_url = await get_running_profile_cdp()
    if cdp_url:
        logger.info(f"🔗 [Chrome] Connecting to running profile via CDP: {cdp_url}")
        return await _search_via_cdp(query, cdp_url, num_results)

    # Fallback to launching a context
    config = ChromeSearchConfig(
        headless=headless,
        profile_dir=profile_dir,
        num_results=num_results,
        binary_location=binary_location
    )

    # Cleanup locks to prevent "Profile in use" errors
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = os.path.join(config.profile_dir, lock)
        if os.path.exists(lock_path):
            try:
                if os.path.islink(lock_path): os.unlink(lock_path)
                else: os.remove(lock_path)
            except Exception as e:
                logger.debug(f"Could not remove lock {lock}: {e}")

    async with async_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            # "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions"
        ]

        try:
            ua = random.choice(USER_AGENTS)
            context = await p.chromium.launch_persistent_context(
                user_data_dir=config.profile_dir,
                headless=config.headless,
                executable_path=config.binary_location,
                args=launch_args,
                user_agent=ua,
                viewport={'width': 1280, 'height': 800},
                ignore_default_args=["--enable-automation"]
            )

            page = context.pages[0] if context.pages else await context.new_page()
            # await playwright_stealth.stealth_async(page)
            
            # Additional stealth: override navigator.webdriver
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            results = await _perform_google_search(page, query, num_results)
            await context.close()
            return results
        except Exception as e:
            logger.error(f"❌ [Chrome] Search Failed: {e}")
            return []

async def _search_via_cdp(query: str, cdp_url: str, num_results: int) -> List[Dict[str, str]]:
    """Perform search by connecting to an existing browser via CDP."""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            # Find an existing page or create a new one in the existing context
            context = browser.contexts[0]
            page = await context.new_page()
            
            results = await _perform_google_search(page, query, num_results)
            
            await page.close()
            # We don't close the browser because it's external
            return results
        except Exception as e:
            logger.error(f"❌ [CDP] Search Failed: {e}")
            return []

async def _perform_google_search(page: Page, query: str, num_results: int) -> List[Dict[str, str]]:
    """Shared logic for navigating and extracting Google results."""
    search_url = build_google_url(query, num_results)
    logger.info(f"🔍 [Chrome] Searching Google: {query}")

    
    # Random delay before navigation
    # await asyncio.sleep(random.uniform(0.5, 1.5))

    
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        # await asyncio.sleep(10)
    except Exception as e:
        logger.warning(f"Initial navigation timeout, retrying... {e}")
        await page.goto(search_url, wait_until="load", timeout=30000)

    # Human-like wait and scroll
    await asyncio.sleep(random.uniform(1.0, 2.5))
    await human_like_scroll(page)

    content = await page.content()
    if "captcha" in content.lower() or "unusual traffic" in content.lower():
        logger.warning("🚨 [Chrome] Google Blocked Traffic (Captcha detected).")
        # Try to save a screenshot for debugging if possible
        try:
            await page.screenshot(path=os.path.join(PROJECT_DIR, "google_blocked.png"))
        except: pass
        
        # If not headless, we could wait for manual solve, but for a proxy we fail fast
        return []
    
    results = await extract_search_results(page, num_results)
    
    if not results:
        logger.warning("⚠️ No search results extracted. Checking page state...")
        # Save page dump for debugging
        try:
            with open(os.path.join(PROJECT_DIR, "page_dump.html"), "w") as f:
                f.write(content)
        except: pass
        
    return results

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    query = sys.argv[1] if len(sys.argv) > 1 else "AI news"
    res = asyncio.run(search_with_chrome(query))
    print(json.dumps(res, indent=2))

