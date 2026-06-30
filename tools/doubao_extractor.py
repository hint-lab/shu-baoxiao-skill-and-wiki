from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def enabled() -> bool:
    return os.getenv("DOUBAO_EXTRACT_ENABLED", "").lower() in {"1", "true", "yes", "on"} and bool(api_key())


def api_key() -> str:
    return os.getenv("DOUBAO_API_KEY") or os.getenv("ARK_API_KEY") or ""


def model_name() -> str:
    return os.getenv("DOUBAO_MODEL") or os.getenv("ARK_MODEL") or ""


def base_url() -> str:
    return (os.getenv("DOUBAO_BASE_URL") or os.getenv("ARK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else {}


def image_content(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() not in IMAGE_SUFFIXES or not path.exists():
        return None
    media = "jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else path.suffix.lower().lstrip(".")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/{media};base64,{encoded}"},
    }


def normalize_model_fields(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "buyer_name",
        "seller_name",
        "item_name",
        "invoice_no",
        "invoice_date",
        "amount_total",
        "currency",
        "title_valid",
        "invoice_kind",
        "payment_method",
        "transaction_date",
        "document_summary",
    }
    result = {key: value for key, value in payload.items() if key in allowed and value not in ("", None, [])}
    if "amount_total" in result:
        try:
            result["amount_total"] = float(str(result["amount_total"]).replace(",", ""))
            result["max_amount"] = result["amount_total"]
        except ValueError:
            result.pop("amount_total", None)
    if "title_valid" in result and not isinstance(result["title_valid"], bool):
        result["title_valid"] = str(result["title_valid"]).lower() in {"true", "yes", "1", "有效", "是"}
    return result


def extract_fields_with_doubao(path: Path, text: str, document_type: str) -> dict[str, Any]:
    if not enabled() or not model_name():
        return {}

    system = (
        "你是高校报销材料识别助手。只输出 JSON，不输出解释。"
        "字段包括 buyer_name, seller_name, item_name, invoice_no, invoice_date, amount_total, currency, "
        "title_valid, invoice_kind, payment_method, transaction_date, document_summary。"
        "无法确定的字段不要编造。国内发票购买方必须精确等于“上海大学”才算 title_valid=true。"
    )
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"文件名：{path.name}\n"
                f"当前本地识别类型：{document_type}\n"
                f"文本内容：\n{text[:6000]}\n\n"
                "请抽取报销字段，返回严格 JSON。"
            ),
        }
    ]
    image = image_content(path)
    if image:
        content.append(image)

    payload = {
        "model": model_name(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
    }
    request = urllib.request.Request(
        f"{base_url()}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(os.getenv("DOUBAO_TIMEOUT", "30"))) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {"model_extract_error": "doubao_request_failed"}

    try:
        content_text = raw["choices"][0]["message"]["content"]
        model_fields = normalize_model_fields(parse_json_object(content_text))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return {"model_extract_error": "doubao_response_parse_failed"}
    if model_fields:
        model_fields["model_extract_provider"] = "doubao"
        model_fields["model_extract_model"] = model_name()
    return model_fields
