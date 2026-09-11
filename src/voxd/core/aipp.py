import requests
import json
import os
import time
from voxd.utils.libw import verbo, verr
from pathlib import Path


def _dispatch_provider(full_prompt: str, provider: str, model: str) -> str:
    if provider == "ollama":
        return run_ollama_aipp(full_prompt, model)
    elif provider == "llamacpp_server":
        return run_llamacpp_server_aipp(full_prompt, model)
    elif provider == "openai":
        return run_openai_aipp(full_prompt, model)
    elif provider == "anthropic":
        return run_anthropic_aipp(full_prompt, model)
    elif provider == "xai":
        return run_xai_aipp(full_prompt, model)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def run_aipp(text: str, cfg, prompt_key: str = None) -> str:
    """
    Run AIPP post-processing on the given text using the selected prompt.
    Retries once on network failure.
    """
    prompts = cfg.data.get("aipp_prompts", {})
    if prompt_key is None:
        prompt_key = cfg.data.get("aipp_active_prompt", "default")
    prompt = prompts.get(prompt_key, "")
    if not prompt:
        prompt = "Summarize this text:"
    full_prompt = f"{prompt}\n{text.strip()}"

    provider = cfg.data.get("aipp_provider", "local")
    # Use the selected model for the current provider
    model = cfg.get_aipp_selected_model(provider) if hasattr(cfg, "get_aipp_selected_model") else cfg.data.get("aipp_model", "llama3.2:latest")

    for attempt in (1, 2):
        try:
            if provider == "local":
                return text
            return _dispatch_provider(full_prompt, provider, model)
        except ValueError as e:
            verr(f"[aipp] {e}")
            return text
        except (requests.RequestException, ConnectionError) as e:
            if attempt == 2:
                verr(f"[aipp] Network error after retry: {e}")
                return text
            verr("[aipp] Network error, retrying once...")
            time.sleep(0.5)


def translate_text(text: str, target_lang: str, cfg) -> str:
    """Translate *text* into *target_lang* (ISO 639-1) via the configured
    LLM provider. Returns the original text when translation is unavailable
    so dictation is never lost."""
    from voxd.utils.languages import code_to_name
    target = (target_lang or "").strip().lower()
    if not text or not text.strip() or not target:
        return text
    prompt = (
        f"Translate the following text to {code_to_name(target)}. "
        f"Respond with only the translation, no explanations or quotes:\n{text.strip()}"
    )
    provider = cfg.data.get("aipp_provider", "local") if cfg else "local"
    try:
        model = cfg.get_aipp_selected_model(provider) if hasattr(cfg, "get_aipp_selected_model") else "llama3.2:latest"
    except Exception:
        model = "llama3.2:latest"
    for attempt in (1, 2):
        try:
            if provider == "local":
                raise ValueError("no LLM provider configured")
            out = _dispatch_provider(prompt, provider, model)
            out = (out or "").strip()
            return out or text
        except ValueError as e:
            verr(f"[translate] {e}")
            return text
        except (requests.RequestException, ConnectionError) as e:
            if attempt == 2:
                verr(f"[translate] Network error after retry: {e}")
                return text
            time.sleep(0.5)
        except Exception as e:
            verr(f"[translate] Error: {e}")
            return text
    return text


def run_ollama_aipp(prompt: str, model: str = "llama3.2:latest") -> str:
    url = "http://localhost:11434/api/generate"
    response = requests.post(url, json={
        "model": model,
        "prompt": prompt,
        "stream": False
    }, timeout=20)
    if response.ok:
        return response.json().get("response", "")
    else:
        raise requests.RequestException(f"Ollama error {response.status_code}: {response.text}")


def run_openai_aipp(prompt: str, model: str = "gpt-3.5-turbo") -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
    if response.ok:
        return response.json()["choices"][0]["message"]["content"].strip()
    else:
        raise requests.RequestException(f"OpenAI error {response.status_code}: {response.text}")


def run_anthropic_aipp(prompt: str, model: str = "claude-3-opus-20240229") -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
    if response.ok:
        return response.json()["content"][0]["text"].strip()
    else:
        raise requests.RequestException(f"Anthropic error {response.status_code}: {response.text}")


def run_xai_aipp(prompt: str, model: str = "grok-3") -> str:
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('XAI_API_KEY', '')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
    if response.ok:
        return response.json()["choices"][0]["message"]["content"].strip()
    else:
        raise requests.RequestException(f"XAI error {response.status_code}: {response.text}")


def run_llamacpp_server_aipp(prompt: str, model: str = "gemma-3-270m") -> str:
    """Use llama.cpp server API (OpenAI-compatible)."""
    from voxd.core.config import get_config
    from voxd.core.llama_server_manager import ensure_server_running
    
    cfg = get_config()
    url = cfg.data.get("llamacpp_server_url", "http://localhost:8080")
    timeout = cfg.data.get("llamacpp_server_timeout", 30)
    
    # Ensure server is running before making API calls
    server_path = cfg.data.get("llamacpp_server_path", "")
    model_path = cfg.get_llamacpp_model_path(model)
    
    if not ensure_server_running(server_path, model_path):
        raise RuntimeError("Failed to start llama-server")
    
    response = requests.post(f"{url}/v1/chat/completions", json={
        "model": model,  # Model name is mostly ignored by llama.cpp server
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": 512,
        "temperature": 0.7
    }, timeout=timeout)
    
    if response.ok:
        return response.json()["choices"][0]["message"]["content"].strip()
    else:
        raise requests.RequestException(f"llama.cpp server error {response.status_code}: {response.text}")


## llamacpp_direct support removed


def get_final_text(transcript: str, cfg) -> str:
    """
    Returns the final text after AIPP post-processing,
    or the raw transcript if AIPP is disabled.
    """
    if not cfg.data.get("aipp_enabled", False):
        return transcript
    prompt_key = cfg.data.get("aipp_active_prompt", "default")
    try:
        return run_aipp(transcript, cfg, prompt_key=prompt_key)
    except Exception as e:
        verr(f"[aipp] Error: {e}")
        return transcript


def get_translated_text(transcript: str, cfg) -> str:
    """Translate *transcript* into the configured translate target.

    Target "en" is handled natively by whisper (--translate); other targets
    go through the LLM provider. Returns the input unchanged when
    translation is off or inapplicable.
    """
    from voxd.core.transcriber import translation_target, use_native_translate
    if not transcript or not transcript.strip():
        return transcript
    target = translation_target(cfg)
    if not target or use_native_translate(cfg):
        return transcript
    try:
        return translate_text(transcript, target, cfg)
    except Exception as e:
        verr(f"[translate] Error: {e}")
        return transcript
