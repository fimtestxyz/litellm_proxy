import asyncio
import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chrome_web_search import search_with_chrome

async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Starting Chrome Headed Search Test...")
    
    query = "LiteLLM Proxy GitHub"
    
    # We set headless=False explicitly for this test
    results = await search_with_chrome(
        query=query, 
        num_results=5, 
        headless=False
    )
    
    print("\n" + "="*50)
    print(f"🔍 Search Results for: '{query}'")
    print("="*50)
    
    if not results:
        print("❌ No results found. Check if Google is blocking or if Chrome failed to launch.")
        return

    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   URL: {r['url']}")
        print(f"   Snippet: {r['description'][:100]}...")
        print("-" * 30)
    
    print(f"\n✅ Test Completed. Found {len(results)} results.")

if __name__ == "__main__":
    asyncio.run(main())
