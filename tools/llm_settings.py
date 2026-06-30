from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path("/Users/hao/Documents/自助报销Agent")
CONFIG_PATH = ROOT / "data/settings/rag_llm.json"

PROVIDER_DEFAULTS = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
    },
    "doubao": {
        "label": "豆包/火山方舟",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "",
    },
    "custom": {
        "label": "自定义 OpenAI 兼容",
        "base_url": "",
        "model": "",
    },
}


def read_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def env_config() -> dict[str, Any]:
    provider = (os.getenv("RAG_LLM_PROVIDER") or "").strip().lower()
    api_key = os.getenv("RAG_LLM_API_KEY") or ""
    if not provider and api_key:
        provider = "deepseek"
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    return {
        "enabled": (os.getenv("RAG_LLM_ENABLED") or "").lower() in {"1", "true", "yes", "on"},
        "provider": provider,
        "base_url": (os.getenv("RAG_LLM_BASE_URL") or defaults.get("base_url") or "").rstrip("/"),
        "model": os.getenv("RAG_LLM_MODEL") or defaults.get("model") or "",
        "api_key": api_key,
    }


def effective_config() -> dict[str, Any]:
    saved = read_config()
    env = env_config()
    provider = str(saved.get("provider") or env.get("provider") or "deepseek").strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    config = {
        "enabled": bool(saved.get("enabled", env.get("enabled", False))),
        "provider": provider,
        "base_url": str(saved.get("base_url") or env.get("base_url") or defaults.get("base_url") or "").rstrip("/"),
        "model": str(saved.get("model") or env.get("model") or defaults.get("model") or ""),
        "api_key": str(saved.get("api_key") or env.get("api_key") or ""),
    }
    return config


def status() -> dict[str, Any]:
    config = effective_config()
    return {
        "enabled": config["enabled"],
        "provider": config["provider"],
        "provider_label": PROVIDER_DEFAULTS.get(config["provider"], PROVIDER_DEFAULTS["custom"])["label"],
        "base_url": config["base_url"],
        "model": config["model"],
        "has_api_key": bool(config["api_key"]),
        "ready": bool(config["enabled"] and config["api_key"] and config["base_url"] and config["model"]),
        "config_path": str(CONFIG_PATH),
    }


def save_config(
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    enabled: bool,
    clear_key: bool = False,
    path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    provider = (provider or "deepseek").strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    current = read_config(path)
    next_api_key = ""
    if clear_key:
        next_api_key = ""
    elif api_key.strip():
        next_api_key = api_key.strip()
    else:
        next_api_key = str(current.get("api_key") or "")
    payload = {
        "enabled": bool(enabled),
        "provider": provider,
        "base_url": (base_url.strip() or defaults.get("base_url") or "").rstrip("/"),
        "model": model.strip() or defaults.get("model") or "",
        "api_key": next_api_key,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return status()
