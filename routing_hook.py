import os
import json
import datetime
import logging
import yaml
from typing import Optional, Dict, Any, List
from litellm.integrations.custom_logger import CustomLogger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_router_hook")

class SmartRouterHook(CustomLogger):
    """
    LiteLLM Custom Logger for Task-Based Model Routing and detailed logging.
    
    This hook intercepts requests for 'smart-proxy' and redirects them to
    specialized Ollama models based on the detected intent.
    The mapping is loaded from route_model_mapping.yaml.
    """
    
    # Defaults as fallback
    DEFAULT_MAPPING = {
        "fast": "ollama/qwen2.5:3b",
        "coding": "ollama/qwen2.5-coder:14b",
        "reasoning": "ollama/llama3:70b-instruct",
        "summary": "ollama/qwen3-vl:4b",
        "flash": "ollama/phi3.5:3.8b"
    }
    
    def __init__(self):
        self.log_dir = "logs/routing"
        os.makedirs(self.log_dir, exist_ok=True)
        self.mapping_file = "route_model_mapping.yaml"
        self.model_mapping = self._load_mapping()
        logger.info(f"Smart router hook initialized. Logs at {self.log_dir}")
        logger.info(f"Loaded model mapping: {self.model_mapping}")

    def _load_mapping(self) -> Dict[str, str]:
        """Load model mapping from YAML file or return defaults."""
        try:
            if os.path.exists(self.mapping_file):
                with open(self.mapping_file, "r") as f:
                    config = yaml.safe_load(f)
                    return config.get("mapping", self.DEFAULT_MAPPING)
            else:
                logger.warning(f"Mapping file {self.mapping_file} not found. Using defaults.")
                return self.DEFAULT_MAPPING
        except Exception as e:
            logger.error(f"Error loading {self.mapping_file}: {e}. Using defaults.")
            return self.DEFAULT_MAPPING
        
    def _save_routing_log(self, log_data: Dict[str, Any]):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        request_id = log_data.get("request_id", "unknown")
        filename = f"route_{timestamp}_{request_id}.json"
        filepath = os.path.join(self.log_dir, filename)
        
        try:
            with open(filepath, "w") as f:
                json.dump(log_data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save routing log: {e}")

    def _detect_intent(self, messages: List[Dict[str, str]]) -> str:
        """
        Analyze message history to determine the best model for the task.
        """
        if not messages:
            return "fast"
            
        # Combine all content for broader context analysis
        last_message = messages[-1].get("content", "").lower() if messages else ""
        full_history = " ".join([m.get("content", "").lower() for m in messages])
        
        # 1. Summarization / Briefing
        summary_keywords = ["summarize", "summary", "tl;dr", "brief", "shorten", "gist", "recap", "tl-dr"]
        if any(kw in last_message for kw in summary_keywords):
            return "summary"
            
        # 2. Coding / Technical Tasks
        coding_keywords = [
            "code", "function", "class", "script", "bug", "fix", "refactor",
            "python", "javascript", "typescript", "rust", "golang", "c++", "c#",
            "implementation", "api endpoint", "database query", "sql", "json",
            "how do i write", "coding", "syntax", "error in my code"
        ]
        if any(kw in last_message for kw in coding_keywords):
            return "coding"
            
        # 3. Deep Reasoning / Complex Logic
        reasoning_keywords = [
            "think step by step", "reason", "analyze", "deep dive", "complex",
            "explain why", "long-form", "philosophical", "architectural",
            "math", "proof", "derivation", "logical", "compare and contrast",
            "implications", "profound", "strategy", "planning"
        ]
        if any(kw in last_message for kw in reasoning_keywords):
            return "reasoning"
            
        # 4. Quick Responses / Chitchat
        flash_keywords = ["hello", "hi", "hey", "thanks", "thank you", "ok", "cool", "chat", "bye", "good morning"]
        if any(kw in last_message for kw in flash_keywords) and len(last_message) < 150:
            return "flash"
            
        # Default fallback
        return "fast"

    async def async_pre_call_hook(
        self,
        **kwargs
    ):
        """
        LiteLLM hook that runs before each model call.
        """
        request_data = kwargs.get("data", {})
        original_model = request_data.get("model", "")
        call_id = kwargs.get("litellm_call_id", "req_" + datetime.datetime.now().strftime("%H%M%S"))
        
        # Only intercept if the model is 'smart-proxy'
        if original_model != "smart-proxy":
            return request_data
            
        messages = request_data.get("messages", [])
        
        log_entry = {
            "request_id": call_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "original_model": original_model,
            "messages": messages,
            "detected_intent": "unknown",
            "target_logical_model": "unknown",
            "target_provider_model": "unknown",
            "status": "pending"
        }
        
        try:
            # 1. Detect Intent
            target_logical = self._detect_intent(messages)
            target_provider = self.model_mapping.get(target_logical, self.model_mapping.get("fast", "ollama/qwen2.5:3b"))
            
            log_entry["detected_intent"] = target_logical
            log_entry["target_logical_model"] = target_logical
            log_entry["target_provider_model"] = target_provider
            
            # 2. Re-route the request
            request_data["model"] = target_provider
            
            # Update kwargs for subsequent loggers/callbacks
            if "model" in kwargs:
                kwargs["model"] = target_provider
                
            # If litellm_params is present, update the model there too
            if "litellm_params" in kwargs:
                kwargs["litellm_params"]["model"] = target_provider
                
            logger.info(f"🔄 [ID:{call_id}] Smart Routing: '{original_model}' -> '{target_logical}' ({target_provider})")
            log_entry["status"] = "success"
            
        except Exception as e:
            logger.error(f"Smart router hook error: {str(e)}")
            request_data["model"] = self.model_mapping.get("fast", "ollama/qwen2.5:3b")
            log_entry["status"] = "error"
            log_entry["error"] = str(e)
            log_entry["target_provider_model"] = self.model_mapping.get("fast", "ollama/qwen2.5:3b")

        # Save detailed log to logs/routing/
        self._save_routing_log(log_entry)

        return request_data

# Instantiate the hook for LiteLLM to use
smart_router_hook = SmartRouterHook()
