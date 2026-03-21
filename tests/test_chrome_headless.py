import asyncio
import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chrome_web_search import search_with_chrome

async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Starting Chrome HEADLESS Search Test...")
    
    query = "LiteLLM Proxy GitHub"
    
    results = await search_with_chrome(
        query=query, 
        num_results=5, 
        headless=True
    )
    
    if results:
        print(f"✅ Success! Found {len(results)} results in headless mode.")
    else:
        print("❌ Failed in headless mode as well.")

if __name__ == "__main__":
    asyncio.run(main())
