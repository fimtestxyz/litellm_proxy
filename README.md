# LiteLLM Reverse Proxy with Web Search Plugin

This project implements a secure, resilient, and extensible AI reverse proxy using LiteLLM.

## Features
- **Unified API:** Acts as an OpenAI-compatible gateway for multiple LLMs (OpenAI, Anthropic, Ollama).
- **Web Search Plugin:** A custom pre-call hook that triggers a web search (Google, DuckDuckGo, or Tavily) for time-sensitive or factual queries, augmenting the prompt with real-time context.
- **Google Search (Native):** Scrapes Google results using a local Chrome profile and Playwright (CDP) for high-quality, stealthy search results.
- **Resilience:** Built-in retries and fallback mechanisms.

## Setup

### Prerequisites
- Python 3.12+ (managed with `uv`)
- Playwright browsers: `uv run playwright install chromium`
- Docker & Docker Compose (optional, for full deployment)

### Environment Variables
Create a `.env` file with the following keys:
```env
OPENAI_API_KEY=your_openai_key
SEARCH_PROVIDER=google  # Options: google, ddgs, tavily, both
ENABLE_GOOGLE_SEARCH=true
```

### Installation
```bash
uv sync
uv run playwright install chromium
```

### Running Tests
```bash
PYTHONPATH=. uv run pytest tests/test_hooks.py
```

### Management Script
We provide a `manage.sh` script to simplify operations on macOS:
```bash
./manage.sh start    # Start natively with uv (Fastest)
./manage.sh status   # Check status of proxy and port
./manage.sh logs     # View live logs
./manage.sh stop     # Stop all services
./manage.sh test     # Run the test suite
```

## Mac Mini M4 Pro Optimization
1. **Native Execution:** Use `./manage.sh start`. Running via `uv` natively on macOS is more efficient than Docker for Python-based proxies.
2. **Ollama & Metal:** Ensure Ollama is installed natively on your Mac. It will automatically use the M4 Pro's GPU/Neural Engine for models like `llama3`.
3. **Low Latency:** The proxy is configured with `uvloop` (via LiteLLM) to take advantage of high-performance event loops on Darwin.

## Architecture
1. **Client** sends an OpenAI-compatible request to the LiteLLM Proxy.
2. **LiteLLM Proxy** runs the `web_search_augmentation` hook from `custom_hooks.py`.
3. If the query triggers a search, it fetches context from the **Tavily API** and injects it into the system message.
4. **LiteLLM Proxy** routes the augmented request to the configured backend model (e.g., Llama3 on Ollama or GPT-4o).
5. The response is streamed back to the client.
