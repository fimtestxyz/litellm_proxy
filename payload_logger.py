import os
import json
import datetime
import logging
from typing import Optional, Any, Dict, List
from litellm.integrations.custom_logger import CustomLogger

# Configure logging for the logger itself
logger = logging.getLogger("payload_logger")

class PayloadLogger(CustomLogger):
    def __init__(self):
        self.log_dir = "payload_logs"
        os.makedirs(self.log_dir, exist_ok=True)

    def _save_log(self, request_id: str, stage: str, data: Any):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{request_id}_{stage}_{timestamp}.json"
        filepath = os.path.join(self.log_dir, filename)
        
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save payload log: {e}")

    async def async_pre_call_hook(self, **kwargs):
        """
        Logs: Client -> Proxy
        """
        # Extract data from the same structure as WebSearchHook
        request_data = kwargs.get("data", {})
        messages = request_data.get("messages", [])
        model = request_data.get("model", "unknown")
        user_api_key_dict = kwargs.get("user_api_key_dict")
        
        request_id = kwargs.get("litellm_call_id") or "req_" + datetime.datetime.now().strftime("%H%M%S")
        log_data = {
            "request_id": request_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "direction": "Client -> Proxy",
            "model": model,
            "messages": messages,
            "user": str(user_api_key_dict) if user_api_key_dict else "None"
        }
        self._save_log(request_id, "1_client_request", log_data)
        return request_data

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        """
        Logs: Proxy -> Client (and implies Proxy -> Provider success)
        """
        request_id = kwargs.get("litellm_call_id", "unknown")
        
        # Log the request sent to provider
        provider_request = {
            "timestamp": start_time.isoformat() if hasattr(start_time, 'isoformat') else str(start_time),
            "direction": "Proxy -> Provider (Ollama/Cloud)",
            "model": kwargs.get("model"),
            "messages": kwargs.get("messages"),
            "provider_params": kwargs.get("litellm_params", {})
        }
        self._save_log(request_id, "2_provider_request", provider_request)

        # Log the response from provider
        provider_response = {
            "timestamp": end_time.isoformat() if hasattr(end_time, 'isoformat') else str(end_time),
            "direction": "Provider -> Proxy -> Client",
            "latency_ms": (end_time - start_time).total_seconds() * 1000 if hasattr(end_time, 'total_seconds') else 0,
            "response": response_obj.model_dump() if hasattr(response_obj, 'model_dump') else str(response_obj)
        }
        self._save_log(request_id, "3_full_response", provider_response)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        """
        Logs failures
        """
        request_id = kwargs.get("litellm_call_id", "unknown")
        error_log = {
            "timestamp": datetime.datetime.now().isoformat(),
            "direction": "Error",
            "error": str(response_obj),
            "kwargs": {k: str(v) for k, v in kwargs.items() if k != "messages"} # Avoid bloat
        }
        self._save_log(request_id, "error", error_log)

payload_logger = PayloadLogger()
