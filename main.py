import os
import asyncio
import httpx
import yaml
import tempfile
import sys
from litellm import run_server

async def get_ollama_models():
    """Scan Ollama for available models via its API."""
    ollama_api_base = os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434")
    
    print("\n" + "═"*60)
    print(" 🔍 OLLAMA MODEL DISCOVERY ".center(60, "═"))
    print("═"*60)
    print(f"📡 Connecting to Ollama at: {ollama_api_base}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ollama_api_base}/api/tags", timeout=5.0)
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            
            if not models:
                print("⚠️  No models found in your Ollama instance.")
                return []

            new_models = []
            print(f"✅ Found {len(models)} models:")
            for m in models:
                model_tag = m["name"]
                size_gb = m.get("size", 0) / (1024**3)
                print(f"   • {model_tag:<30} ({size_gb:.2f} GB)")
                
                new_models.append({
                    "model_name": model_tag,
                    "litellm_params": {
                        "model": f"ollama/{model_tag}",
                        "api_base": ollama_api_base,
                        "stream": True
                    }
                })
            return new_models
    except Exception as e:
        print(f"❌ Error during Ollama discovery: {str(e)}")
        print("   Make sure Ollama is running and OLLAMA_API_BASE is correct.")
        return []
    finally:
        print("═"*60 + "\n")

def run_proxy():
    """Load config, inject discovered models, and start the proxy."""
    config_file = os.getenv("CONFIG_FILE", "litellm_config.yaml")
    port = os.getenv("PORT", "4000")
    
    # 1. Load existing config
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"⚠️  Config file {config_file} not found. Creating a fresh one.")
        config = {"model_list": [], "litellm_settings": {}}
    
    # 2. Get Ollama models (Run the async function synchronously)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ollama_models = loop.run_until_complete(get_ollama_models())
    except Exception as e:
        print(f"❌ Async discovery failed: {e}")
        ollama_models = []
    
    # 3. Add to config if not already there
    if "model_list" not in config:
        config["model_list"] = []
    
    # Keep existing models, but add discovered ones if they don't clash
    #
    # We will be flexible with the ':latest' tag. If a model 'x' is in the
    # config, and the discovered model is 'x:latest', we treat them as the
    # same and skip the discovered one.
    existing_model_names = {m.get("model_name", "").split(":")[0] for m in config["model_list"] if isinstance(m, dict)}

    added_count = 0
    skipped_count = 0
    for nm in ollama_models:
        # Normalize by removing ':latest' and then the part after ':'
        discovered_name = nm["model_name"]
        
        # Get the base name (e.g., 'qwen3.5' from 'qwen3.5:latest')
        base_name = discovered_name.split(":")[0]

        if base_name not in existing_model_names:
            config["model_list"].append(nm)
            added_count += 1
        else:
            print(f"ℹ️  Skipping discovered model '{discovered_name}' as '{base_name}' is already in the config.")
            skipped_count += 1
            
    if added_count > 0:
        print(f"🚀 Injected {added_count} newly discovered models into the proxy configuration.")
    
    if skipped_count == 0 and added_count == 0:
        print("ℹ️  All discovered models were already in the config.")

    # 4. Create a temporary config file in the current directory
    # This ensures that relative imports like 'custom_hooks' still work
    tmp_path = os.path.join(os.getcwd(), ".tmp_litellm_config.yaml")
    with open(tmp_path, "w") as tmp:
        yaml.dump(config, tmp)
    
    print(f"🚀 Starting LiteLLM Proxy on port {port}...")
    
    # 5. Start the proxy server
    try:
        # Prepare sys.argv for litellm.run_server()
        sys.argv = [sys.argv[0], "--config", tmp_path, "--port", str(port)]
        run_server()
    except Exception as e:
        print(f"❌ Failed to start proxy: {e}")
    finally:
        # Clean up
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    if "--discover" in sys.argv:
        asyncio.run(get_ollama_models())
    else:
        run_proxy()
