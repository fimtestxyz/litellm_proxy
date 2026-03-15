AI reverse proxy layer which act between a AI code agent/cli to LLM provider and ollama models. the reverse proxy layer is secure, resilient, scalable, maintainable and extensible with plugin. one plugin is to allow web search
---

### 1. Strategic Pivot: Build vs. Orchestrate

| Feature | Custom Go/Rust Proxy (Previous Plan) | LiteLLM Proxy (New Plan) |
| :--- | :--- | :--- |
| **Core Logic** | Build from scratch | **Use LiteLLM Proxy** (Handles normalization, streaming, auth) |
| **Routing** | Custom logic | **LiteLLM Router** (Built-in fallbacks, load balancing) |
| **Plugins** | WASM / gRPC | **Python Hooks / Guardrails** (Easier to write, less isolated) |
| **State** | Custom Redis implementation | **Native Redis Integration** (Caching, Rate Limit, Budget) |
| **Maintenance** | High (You own the core) | **Low** (Upstream LiteLLM updates) |
| **Performance** | Extremely High (Binary) | **High** (Async Python/FastAPI) |

---

### 2. Redesigned Architecture

The system is now centered around the **LiteLLM Proxy Container**, extended by custom Python modules mounted as volumes.

```mermaid
graph TD
    Client[AI Code Agent / CLI] -->|HTTPS | Ingress[Nginx / Traefik]
    Ingress -->|TLS Termination | LiteLLM[LiteLLM Proxy Server]
    
    subgraph "LiteLLM Proxy Container"
        API[API Layer<br/>OpenAI Compatible]
        Auth[Auth & Budgeting]
        Router[Smart Router]
        Hooks[Custom Hooks / Guardrails]
    end
    
    LiteLLM --> API --> Auth --> Hooks --> Router
    
    subgraph "Plugin Logic (Python)"
        WebSearch[Web Search Hook]
        PII[PII Guardrail]
    end
    
    Hooks -.-> WebSearch
    Hooks -.-> PII
    
    subgraph "State Layer"
        Redis[(Redis Cluster)<br/>Cache, Rate Limit, Logs]
    end
    
    LiteLLM <--> Redis
    
    subgraph "Backend Models"
        Ollama[(Ollama)]
        Cloud[(OpenAI / Anthropic)]
    end
    
    Router -->|Local | Ollama
    Router -->|Cloud | Cloud
    
    style LiteLLM fill:#ff9999,stroke:#333,stroke-width:2px
    style Hooks fill:#99ccff,stroke:#333,stroke-width:2px
```

---

### 3. Key Components & Implementation

#### A. Core Engine: LiteLLM Proxy
You will run the official `ghcr.io/berriai/litellm` Docker image. It provides:
*   **Unified API:** Automatically converts Ollama/Anthropic responses to OpenAI format.
*   **Streaming:** Native Server-Sent Events (SSE) support.
*   **Authentication:** Virtual Keys, Team management, and Spend tracking.
*   **Resilience:** Built-in retries, timeouts, and fallbacks (e.g., if Ollama fails, fallback to GPT-4).

#### B. The Plugin System: Custom Guardrails & Hooks
LiteLLM allows you to inject Python code at specific stages of the request lifecycle. This is where your **Web Search** plugin lives.

*   **Mechanism:** `custom_guardrail.py` or `callback.py`.
*   **Security Note:** Since plugins run in the same Python process as the proxy, ensure you pin dependencies strictly in a `requirements.txt` mounted into the container.

#### C. State & Resilience: Redis
LiteLLM relies heavily on Redis for:
*   **Caching:** Store LLM responses to save costs/latency.
*   **Rate Limiting:** Token-based or Request-based limits per API Key.
*   **Logging:** Store request/response logs for auditing.

---

### 4. Implementing the Web Search Plugin

In the LiteLLM ecosystem, you don't build a "middleware server." You write a Python function that registers as a **Pre-Call Hook**.

**File:** `custom_hooks.py` (Mounted into the container)

```python
import os
import httpx
from litellm.types.guardrails import GuardrailEventHooks
from litellm.proxy.guardrails.guardrail_helpers import should_proceed

async def web_search_augmentation(kwargs):
    """
    This function runs BEFORE the LLM is called.
    It inspects the messages, searches if needed, and injects context.
    """
    messages = kwargs.get("messages", [])
    last_message = messages[-1]["content"] if messages else ""

    # 1. Simple Intent Detection (Can be enhanced with a small classifier)
    search_keywords = ["search", "latest", "news", "current", "2024", "2025"]
    if not any(k in last_message.lower() for k in search_keywords):
        return kwargs # No search needed

    # 2. Perform Search (Async)
    async with httpx.AsyncClient() as client:
        try:
            # Example using Tavily or similar
            response = await client.post(
                "https://api.tavily.com/search", 
                json={"query": last_message, "api_key": os.getenv("TAVILY_KEY")}
            )
            results = response.json()
            
            # 3. Format Context
            context_text = "\n".join([f"- {r['title']}: {r['content']}" for r in results['results'][:3]])
            
            # 4. Inject into System Message or User Message
            system_prompt = f"\n\n[WEB SEARCH CONTEXT]\n{context_text}\n[/WEB SEARCH CONTEXT]\n"
            
            # Check if system message exists
            if messages[0]["role"] == "system":
                messages[0]["content"] += system_prompt
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})
                
            kwargs["messages"] = messages
            
        except Exception as e:
            print(f"Search plugin failed: {e}")
            # Fail silently to ensure resilience
            
    return kwargs

# Register the hook with LiteLLM
# This mapping is defined in litellm_config.yaml
```

---

### 5. Configuration (`litellm_config.yaml`)

This is the control plane for your proxy.

```yaml
model_list:
  # Local Model
  - model_name: "llama3"
    litellm_params:
      model: "ollama/llama3"
      api_base: "http://ollama:11434"
      stream: true
  
  # Cloud Fallback
  - model_name: "llama3"
    litellm_params:
      model: "gpt-4-turbo"
      api_key: "os.environ/OPENAI_API_KEY"
      stream: true

litellm_settings:
  # Resilience
  set_verbose: true
  drop_params: true
  retry: true
  num_retries: 3
  
  # Caching & State
  cache: true
  cache_params:
    type: "redis"
    host: "redis"
    port: 6379
    
  # Rate Limiting
  redis_url: "redis://redis:6379"

  # Plugin Registration
  guardrails:
    - id: "web-search-plugin"
      path: "custom_hooks.py" 
      # This tells LiteLLM to load your custom python file
      callback: "web_search_augmentation" 
      event_hook: "pre_call" # Run before sending to LLM

general_settings:
  master_key: "sk-1234" # Your master admin key
  database_url: "postgresql://..." # For tracking spend/keys
```

---

### 6. Deployment Strategy (Docker Compose)

This setup ensures scalability and maintainability.

```yaml
version: '3.8'
services:
  litellm-proxy:
    image: ghcr.io/berriai/litellm:main-latest
    ports:
      - "4000:4000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/litellm
      - REDIS_URL=redis://redis:6379
      - TAVILY_KEY=${TAVILY_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./litellm_config.yaml:/app/config.yaml
      - ./custom_hooks.py:/app/custom_hooks.py # Mount Plugin
    command: >
      --config /app/config.yaml
      --port 4000
    
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - litellm-proxy

volumes:
  ollama_data:
```

---

### 7. Security & Resilience Enhancements

Since we are relying on LiteLLM, we configure its native features rather than building new ones:

1.  **API Key Management:**
    *   Use LiteLLM's **Virtual Keys**. You can generate keys with specific budgets, time limits, and allowed models.
    *   *Command:* `litellm --config config.yaml --create_key`
2.  **Rate Limiting:**
    *   Configured in `litellm_config.yaml` under `litellm_settings`. It uses Redis tokens to limit requests per key.
3.  **PII Redaction (Plugin 2):**
    *   Use LiteLLM's built-in **Presidio Guardrail**. You don't need to write code for this.
    *   Add `guardrails: ["presidio"]` to your config to automatically detect and mask emails/phones before they hit the LLM.
4.  **Observability:**
    *   LiteLLM has a built-in **UI Dashboard** (Hosted or Self-hosted) to view logs, spend, and latency.
    *   Enable Langfuse or Prometheus callbacks in the config for advanced metrics.

---

### 8. Pros & Cons of the LiteLLM Approach

| Feature | Pros | Cons |
| :--- | :--- | :--- |
| **Development Speed** | **Very Fast.** You skip months of proxy dev. | **Dependency Risk.** You rely on LiteLLM's release cycle. |
| **Plugin Security** | Easy to write in Python. | **Less Isolated.** Plugins run in the main process (no WASM sandbox). |
| **Streaming** | Native, robust support for all providers. | Python async overhead (negligible for most cases). |
| **Routing** | Advanced (Weighted routing, fallbacks, latency-based). | Configuration can get complex for very large setups. |
| **Maintainability** | Community maintained core. | You must maintain your custom Python hooks. |

### 9. Recommendation

**Adopt the LiteLLM Proxy strategy.**

Building a production-grade streaming proxy with auth, caching, and multi-provider support is a massive undertaking. LiteLLM solves 90% of your requirements out of the box.

**Your focus should be:**
1.  **Writing the `custom_hooks.py`** for the Web Search logic.
2.  **Hardening the `litellm_config.yaml`** for routing and rate limits.
3.  **Setting up the Nginx/Traefik layer** for TLS and DDoS protection (since LiteLLM is Python, you don't want it exposed directly to the public internet without a web server front).

This approach gives you a **Secure, Resilient, and Extensible** layer in days rather than months.
