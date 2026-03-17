"""
Web Search Results Storage Module for LiteLLM Proxy.

This module handles saving web search results to local files
for logging and debugging purposes.
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("search_storage")

# Storage directory
STORAGE_DIR = "web_search"

def get_storage_dir() -> str:
    """Get or create the storage directory."""
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR)
        logger.info(f"Created storage directory: {STORAGE_DIR}")
    return STORAGE_DIR


def generate_filename(provider: str = "duckduckgo", query: Optional[str] = None) -> str:
    """
    Generate a filename with provider prefix, query slug, and timestamp suffix.
    
    Args:
        provider: Search provider name (default: duckduckgo)
        query: Optional search query to create a slug from
        
    Returns:
        Filename string: provider_queryslug_timestamp.json
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    slug = ""
    if query:
        # Create a URL-safe slug from the query
        slug = re.sub(r'[^a-zA-Z0-9\s]', '', query.lower())
        slug = re.sub(r'\s+', '_', slug).strip('_')
        slug = slug[:50]
        if slug:
            slug = f"_{slug}"
            
    # If no slug, add microsecond to avoid collisions
    if not slug:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
    return f"{provider}{slug}_{timestamp}.json"


def convert_to_serializable(obj: Any) -> Any:
    """
    Convert objects to JSON-serializable format.
    
    Handles datetime objects, sets, and other non-serializable types.
    """
    from datetime import datetime as dt_class
    
    # Check for datetime type directly (not isinstance which can fail)
    if type(obj) == dt_class or type(obj).__name__ == 'datetime':
        return obj.isoformat()
    elif type(obj) == tuple:
        return [convert_to_serializable(item) for item in obj]
    elif type(obj) == set:
        return [convert_to_serializable(item) for item in obj]
    elif type(obj) == dict:
        return {str(k): convert_to_serializable(v) for k, v in obj.items()}
    elif type(obj) == list:
        return [convert_to_serializable(item) for item in obj]
    else:
        return obj


def save_search_results(
    query: str,
    results: List[Dict[str, Any]],
    provider: str = "duckduckgo",
    temporal_info: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Save search results to a JSON file.
    
    Args:
        query: The original search query
        results: List of search result dictionaries
        provider: Search provider name
        temporal_info: Optional temporal parsing info
        metadata: Optional additional metadata
            
    Returns:
        Path to the saved file
    """
    storage_dir = get_storage_dir()
    filename = generate_filename(provider, query)
    filepath = os.path.join(storage_dir, filename)
    
    # Convert temporal_info to serializable format
    temporal_info_serializable = convert_to_serializable(temporal_info) if temporal_info else None
    metadata_serializable = convert_to_serializable(metadata) if metadata else None
    
    # Build the data structure
    data = {
        "query": query,
        "provider": provider,
        "timestamp": datetime.now().isoformat(),
        "result_count": len(results),
        "temporal_info": temporal_info_serializable,
        "metadata": metadata_serializable,
        "results": results
    }
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(results)} search results to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to save search results: {e}")
        return ""


def load_search_results(filepath: str) -> Optional[Dict[str, Any]]:
    """
    Load search results from a file.
    
    Args:
        filepath: Path to the JSON file
        
    Returns:
        Dictionary with search results or None if failed
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load search results from {filepath}: {e}")
        return None


def list_search_results(provider: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    List recent search result files.
    
    Args:
        provider: Filter by provider (optional)
        limit: Maximum number of results to return
            
    Returns:
        List of search result metadata
    """
    storage_dir = get_storage_dir()
    files = []
    
    try:
        for filename in os.listdir(storage_dir):
            if not filename.endswith('.json'):
                continue
                
            if provider and not filename.startswith(provider):
                continue
                
            filepath = os.path.join(storage_dir, filename)
            stat = os.stat(filepath)
            
            files.append({
                "filename": filename,
                "filepath": filepath,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
            
    except Exception as e:
        logger.error(f"Failed to list search results: {e}")
    
    # Sort by modified time, newest first
    files.sort(key=lambda x: x['modified'], reverse=True)
    
    return files[:limit]


def get_search_results_by_query(query: str, provider: str = "duckduckgo") -> Optional[Dict[str, Any]]:
    """
    Find and load the most recent search results for a query.
    
    Args:
        query: Search query to find
        provider: Filter by provider
            
    Returns:
        Search results dictionary or None
    """
    files = list_search_results(provider=provider, limit=50)
    
    for file_info in files:
        data = load_search_results(file_info['filepath'])
        if data and data.get('query', '').lower() == query.lower():
            return data
    
    return None


def clear_old_results(days: int = 7) -> int:
    """
    Clear search results older than specified days.
    
    Args:
        days: Number of days to keep (default: 7)
        
    Returns:
        Number of files deleted
    """
    storage_dir = get_storage_dir()
    cutoff = datetime.now().timestamp() - (days * 86400)
    deleted = 0
    
    try:
        for filename in os.listdir(storage_dir):
            filepath = os.path.join(storage_dir, filename)
            if os.path.isfile(filepath):
                if os.stat(filepath).st_mtime < cutoff:
                    os.remove(filepath)
                    deleted += 1
                    
        if deleted > 0:
            logger.info(f"Cleared {deleted} old search result files")
            
    except Exception as e:
        logger.error(f"Failed to clear old results: {e}")
    
    return deleted


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)
    
    # Test saving
    test_results = [
        {"title": "Test Result 1", "url": "https://example.com/1", "description": "Description 1"},
        {"title": "Test Result 2", "url": "https://example.com/2", "description": "Description 2"}
    ]
    
    filepath = save_search_results(
        query="test query",
        results=test_results,
        provider="duckduckgo",
        temporal_info={"description": "past week"},
        metadata={"model": "qwen3.5"}
    )
    
    print(f"✅ Saved to: {filepath}")
    
    # Test listing
    print("\n📁 Recent search results:")
    for f in list_search_results(limit=5):
        print(f"  - {f['filename']} ({f['size']} bytes)")
