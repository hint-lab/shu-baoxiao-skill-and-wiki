from __future__ import annotations

import json
import re
import http.client
import urllib.error
import urllib.request
from typing import Any

from tools.llm_settings import effective_config


def _chat_completion_content(
    config: dict[str, Any],
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    timeout: int = 45,
) -> dict[str, Any]:
    if not config.get("enabled"):
        return {"enabled": False, "content": "", "error": ""}
    if not (config.get("api_key") and config.get("base_url") and config.get("model")):
        return {"enabled": True, "content": "", "error": "llm_not_configured"}

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
    }
    url = f"{config['base_url'].rstrip('/')}/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
    except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        return {
            "enabled": True,
            "content": "",
            "error": f"llm_request_failed:{type(exc).__name__}",
            "provider": config.get("provider", ""),
            "model": config.get("model", ""),
        }
    return {
        "enabled": True,
        "content": str(content).strip(),
        "error": "",
        "provider": config.get("provider", ""),
        "model": config.get("model", ""),
    }


def fallback_home_intent(note: str, has_files: bool) -> dict[str, Any]:
    text = (note or "").strip()
    if has_files:
        return {
            "intent": "reimbursement_package",
            "action": "create_package",
            "confidence": 0.7,
            "reply": "我先按报销材料整理并生成报销包。",
            "search_query": "",
            "title": "",
        }
    if re.search(r"[?？]|^(怎么|如何|为什么|哪些|什么|能否|能不能|可不可以|是否)", text) or re.search(
        r"(怎么|如何).*(报销|办理|申请)|(报销).*(怎么|如何)|"
        r"(需要|要|准备|提供|提交).*(什么|哪些|材料|附件|手续|证明)|"
        r"(报销|发票).*(要求|规定|标准|流程|材料|附件|依据)",
        text,
    ):
        return {
            "intent": "policy_question",
            "action": "answer_policy",
            "confidence": 0.65,
            "reply": "我先查财务处资料库，再给你带依据的回答。",
            "search_query": text,
            "title": "",
        }
    if re.search(r"(发票|票据|报销|付款|支付|合同|会议|酒店|高铁|火车票|机票|差旅|住宿|版面费|邮费|快递费|邮寄费|办公用品|耗材)", text):
        return {
            "intent": "material_collection",
            "action": "create_inbox",
            "confidence": 0.65,
            "reply": "我先把这条记录放进资料归集，后面补材料后再生成报销包。",
            "search_query": "",
            "title": "",
        }
    return {
        "intent": "clarify",
        "action": "ask_clarification",
        "confidence": 0.45,
        "reply": "你是想查政策依据、记录一个待报销事项，还是已经有发票要整理成报销包？",
        "search_query": "",
        "title": "",
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("home intent response is not an object")
    return payload


def analyze_home_intent(note: str, title: str = "", file_names: list[str] | None = None, conversation_context: str = "") -> dict[str, Any]:
    file_names = file_names or []
    fallback = fallback_home_intent(note, bool(file_names))
    config = effective_config()
    system = (
        "你是上海大学自助报销 Agent 的首页意图分析器。"
        "你只判断用户下一步想做什么，不编造政策答案。"
        "必须只返回 JSON 对象，不要 Markdown，不要解释。"
        "字段：intent, action, confidence, reply, search_query, title。"
        "intent 只能是 policy_question, material_collection, reimbursement_package, clarify。"
        "action 只能是 answer_policy, create_inbox, create_package, ask_clarification。"
        "规则：如果用户在问报销政策、材料要求、能不能报，action=answer_policy；"
        "如果用户描述一件待报销事项但没有上传材料，action=create_inbox；"
        "如果上传了发票或附件且不像单纯问政策，action=create_package；"
        "如果含糊不清，action=ask_clarification。"
        "如果当前输入包含“这个、刚才、上面、继续、它”等指代词，必须结合 conversation_context 判断。"
        "reply 用一句中文告诉用户你准备怎么处理。"
    )
    user = json.dumps(
        {
            "title": title,
            "note": note,
            "conversation_context": conversation_context,
            "has_files": bool(file_names),
            "file_names": file_names[:12],
        },
        ensure_ascii=False,
    )
    result = _chat_completion_content(
        config,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        timeout=30,
    )
    if result.get("error") or not result.get("content"):
        return {**fallback, "mode": "fallback", "llm_error": result.get("error", "")}
    try:
        payload = _extract_json_object(result["content"])
    except (json.JSONDecodeError, ValueError):
        return {**fallback, "mode": "fallback", "llm_error": "invalid_json"}

    allowed_actions = {"answer_policy", "create_inbox", "create_package", "ask_clarification"}
    action = str(payload.get("action") or fallback["action"])
    if action not in allowed_actions:
        action = fallback["action"]
    if fallback["action"] == "answer_policy" and action != "answer_policy":
        action = "answer_policy"
    intent = str(payload.get("intent") or fallback["intent"])
    if action == "answer_policy":
        intent = "policy_question"
    return {
        "intent": intent,
        "action": action,
        "confidence": float(payload.get("confidence") or fallback["confidence"]),
        "reply": str(payload.get("reply") or fallback["reply"]).strip(),
        "search_query": str(payload.get("search_query") or note or "").strip(),
        "title": str(payload.get("title") or title or "").strip(),
        "mode": "llm",
        "provider": result.get("provider", ""),
        "model": result.get("model", ""),
    }


def build_context(hits: list[dict[str, Any]], max_chars: int = 5200) -> str:
    blocks: list[str] = []
    used = 0
    for hit in hits:
        snippet = (hit.get("snippet") or "").strip()
        if not snippet:
            continue
        block = (
            f"[{hit['rank']}]\n"
            f"标题：{hit.get('title', '')}\n"
            f"来源：{hit.get('url', '')}\n"
            f"片段：{snippet}\n"
        )
        if used + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        used += len(block)
    return "\n".join(blocks)


def generate_rag_answer(query: str, hits: list[dict[str, Any]]) -> dict[str, Any]:
    config = effective_config()
    if not config.get("enabled"):
        return {"enabled": False, "answer": "", "error": ""}
    if not (config.get("api_key") and config.get("base_url") and config.get("model")):
        return {"enabled": True, "answer": "", "error": "llm_not_configured"}
    if not hits:
        return {"enabled": True, "answer": "", "error": "no_context"}

    system = (
        "你是上海大学报销知识库助手。只能依据用户给出的检索来源回答。"
        "如果来源不足以确定答案，必须明确说资料不足。"
        "回答要简洁，列出需要的材料、注意事项，并在关键句后标注来源编号，例如 [1]。"
        "不要编造政策，不要替代财务处最终审核口径。"
    )
    user = (
        f"用户问题：{query}\n\n"
        f"检索来源：\n{build_context(hits)}\n\n"
        "请基于以上来源回答。"
    )
    result = _chat_completion_content(
        config,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        timeout=45,
    )
    if result.get("error"):
        return {
            "enabled": True,
            "answer": "",
            "error": result["error"],
            "provider": result.get("provider", config.get("provider", "")),
            "model": result.get("model", config.get("model", "")),
        }
    return {
        "enabled": True,
        "answer": result["content"],
        "error": "",
        "provider": config.get("provider", ""),
        "model": config.get("model", ""),
    }
