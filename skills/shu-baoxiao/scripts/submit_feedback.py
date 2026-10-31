#!/usr/bin/env python3
"""Prepare feedback offline, or submit redacted text after an explicit user request.

Primary channel is an anonymous Feishu form; no public POST endpoint is configured.
Optional GitHub submission uses the caller's GitHub CLI. No credentials are bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO = "hint-lab/shu-baoxiao-skill-and-wiki"
ISSUES_URL = "https://github.com/" + REPO + "/issues"
FEEDBACK_CONFIG = SKILL_ROOT / "references/knowledge/feedback-config.json"
TEXT_LIMITS = {
    "college": 80, "funding_type": 80, "business_month": 30,
    "item_or_matter": 120, "checklist_id": 80, "used_version": 80,
    "environment": 160, "original_claim": 800, "actual_feedback": 1200,
    "outcome": 80, "suggested_correction": 800,
}
ALLOWED_FIELDS = {"schema_version", "category", "privacy_checked", "public_sources", *TEXT_LIMITS}


def check_text(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) > TEXT_LIMITS[field]:
        raise ValueError(f"{field} 必须是限定长度内的脱敏文字。")
    value = value.strip()
    if (re.search(r"\d{8,}|@[A-Za-z0-9_]|/Users/|/home/|[A-Za-z]:\\|file://", value)
            or re.search(r"https?://|!\[[^]]*\]\(|(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._~-]{16,}", value, re.I)):
        raise ValueError(f"{field} 含可能的标识、联系方式、私有路径或链接，请由宿主先脱敏；公开依据放入public_sources。")
    return value


def check_public_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 1000 or re.search(r"[\s<>]", value):
        raise ValueError("公开依据必须是公开网页URL，不能包含附件或个人信息。")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    school_or_government = host == "shu.edu.cn" or host.endswith(".shu.edu.cn") or host.endswith(".gov.cn")
    project = host == "github.com" and (parsed.path == "/" + REPO or parsed.path.startswith("/" + REPO + "/"))
    if parsed.scheme != "https" or parsed.port not in {None, 443} or parsed.username or parsed.password or not (school_or_government or project or host == "docs.github.com"):
        raise ValueError("公开依据仅接受学校、政府、项目仓库或GitHub官方文档的公开HTTPS链接。")
    if parsed.fragment or any(re.search(r"token|signature|credential|auth|password|secret|session|(?:^|_)key$|(?:^|_)code$", key, re.I)
                              for key, _ in parse_qsl(parsed.query)):
        raise ValueError("公开依据含可能的访问凭据或私有链接参数，请改用公开发布页。")
    return value


def prepare_feedback(payload: dict) -> dict:
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1 or set(payload) - ALLOWED_FIELDS:
        raise ValueError("仅接受schema_version=1的固定脱敏字段；不接收附件、自由正文或其他未知字段。")
    if payload.get("privacy_checked") is not True:
        raise ValueError("宿主尚未确认脱敏检查完成，不能准备对外提交的正文。")
    category = payload.get("category", "rule")
    if not isinstance(category, str) or category not in {"rule", "usage"}:
        raise ValueError("category须为rule或usage。")
    values = {field: check_text(payload.get(field, ""), field) for field in TEXT_LIMITS}
    if not values["item_or_matter"] or not values["actual_feedback"]:
        raise ValueError("请补充事项和实际问题；未知的学院、经费或办理状态可留空，不猜测。")
    sources = payload.get("public_sources", [])
    if not isinstance(sources, list) or len(sources) > 5:
        raise ValueError("公开依据最多5条。")
    sources = [check_public_url(value) for value in sources]
    context = values["checklist_id"]
    if context:
        templates = json.loads((SKILL_ROOT / "references/knowledge/checklists.json").read_text(encoding="utf-8"))["templates"]
        if context not in {item["id"] for item in templates}:
            raise ValueError("未知清单ID，不能将个人材料或自由文字作为清单标识。")
    canonical = {"category": category, **values, "public_sources": sources}
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    marker = f"<!-- shu-baoxiao-feedback:{digest} -->"
    tool_version = json.loads((SKILL_ROOT / "references/knowledge/manifest.json").read_text(encoding="utf-8"))["skill_version"]
    labels = [("学院或部门", "college"), ("经费类型", "funding_type"), ("业务年月", "business_month"),
              ("事项/物品", "item_or_matter"), ("关联清单", "checklist_id"), ("使用环境", "environment"),
              ("知识库/AI原判断", "original_claim"), ("实际告知或问题（脱敏）", "actual_feedback"),
              ("办理状态（用户报告）", "outcome"), ("希望核对或修正", "suggested_correction")]
    body = ["本反馈由宿主AI根据使用者陈述整理；内容待维护者核对，不代表已核验规则。", "",
            "使用者报告的Skill/资料包版本：" + html.escape(values["used_version"] or "未说明", quote=False),
            "反馈整理工具版本：" + html.escape(tool_version, quote=False), ""]
    for label, field in labels:
        text = html.escape(values[field] or "未说明", quote=False)
        body.extend(["### " + label, "", "> " + text.replace("\n", "\n> "), ""])
    body.extend(["### 公开依据", ""] + (["- <" + url + ">" for url in sources] or ["未提供；不据此伪造书面来源。"])
                + ["", marker])
    return {"status": "prepared", "submitted": False, "feedback_id": digest, "marker": marker,
            "repository": REPO, "prepared_with_version": tool_version,
            "issue_title": ("[报销反馈] " if category == "rule" else "[使用反馈] ") + values["item_or_matter"],
            "issue_body": "\n".join(body) + "\n", "issues_url": ISSUES_URL,
            "notice": "仅准备脱敏正文；只有用户明确请求提交后才可调用--submit或已授权的GitHub工具。自动检查不能替代宿主对姓名等隐私的检查。"}


def prepare_form_feedback(payload: dict, *, submit: bool = False) -> dict:
    """Validate locally and prepare browser fields; never POST to a webpage URL."""
    prepared = prepare_feedback(payload)
    config = json.loads(FEEDBACK_CONFIG.read_text(encoding="utf-8"))
    values = {field: check_text(payload.get(field, ""), field) for field in TEXT_LIMITS}
    original = values["original_claim"]
    if values["checklist_id"]:
        original = "关联清单：" + values["checklist_id"] + "\n" + original
    actual = values["actual_feedback"]
    if values["suggested_correction"]:
        actual += "\n希望核对或修正：" + values["suggested_correction"]
    if values["environment"]:
        actual += "\n使用环境：" + values["environment"]
    return {"status": "browser_required" if submit else "prepared", "submitted": False,
            "channel": "feishu_form", "feedback_id": prepared["feedback_id"],
            "feedback_url": config["form_url"], "requires_account": False,
            "api": config["api"], "visibility": config["visibility"],
            "form_fields": {"反馈类别": "报销口径或清单" if payload.get("category", "rule") == "rule" else "使用问题",
                            "学院": values["college"], "经费类型": values["funding_type"],
                            "业务年月": values["business_month"], "事项或物品": values["item_or_matter"],
                            "原判断": original, "实际差异": actual, "办理状态": values["outcome"],
                            "使用版本": values["used_version"], "公开依据": "\n".join(payload.get("public_sources", []))},
            "prepared_with_version": prepared["prepared_with_version"],
            "notice": "仅准备脱敏字段，尚未上传。API未配置；宿主应使用浏览器填写匿名表单并核对提交成功页，不能直接向表单URL发POST。没有浏览器工具则提供链接和草稿。自动检查不能替代隐私核对。"}


class GitHubFailure(RuntimeError):
    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


def gh_call(gh: str, args: list[str], runner, timeout: int = 20) -> str:
    result = runner([gh, *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        match = re.search(r"HTTP (401|403|404|410|422|429)\b", result.stderr or "")
        raise GitHubFailure("GitHub调用未成功；不回显可能含凭据的原始输出。", int(match.group(1)) if match else None)
    return result.stdout


def api(gh: str, endpoint: str, runner):
    return json.loads(gh_call(gh, ["api", "--hostname", "github.com", endpoint], runner))


def valid_issue(issue, actor: str, marker: str) -> bool:
    if not isinstance(issue, dict) or "pull_request" in issue:
        return False
    user = issue.get("user") or {}
    if not isinstance(user, dict):
        return False
    number = issue.get("number")
    return (type(number) is int and number > 0
            and issue.get("html_url") == ISSUES_URL + "/" + str(number)
            and str(user.get("login", "")).lower() == actor.lower()
            and isinstance(issue.get("body"), str) and marker in issue["body"])


def find_existing(gh: str, actor: str, marker: str, runner):
    endpoint = f"repos/{REPO}/issues?" + urlencode({"creator": actor, "state": "all", "sort": "created", "direction": "desc", "per_page": 100})
    issues = api(gh, endpoint, runner)
    if not isinstance(issues, list):
        raise GitHubFailure("未取得可核对的反馈列表。")
    return next((issue for issue in issues if valid_issue(issue, actor, marker)), None)


def store_receipt(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".shu-feedback-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({**data, "updated_at": datetime.now(timezone.utc).isoformat()}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def submit_github_feedback(payload: dict, payload_path: Path, *, submit: bool = False,
                    receipt_path: Path | None = None, runner=None, which=None) -> dict:
    prepared = prepare_feedback(payload)
    if not submit:
        return prepared
    if payload_path.resolve().is_relative_to(SKILL_ROOT.resolve()) or (
            receipt_path is not None and receipt_path.resolve().is_relative_to(SKILL_ROOT.resolve())):
        raise ValueError("真实反馈和回执须保存在授权的本地事项或临时目录，不能写入共享Skill资料目录。")
    runner = runner or subprocess.run
    gh = (which or shutil.which)("gh")
    base = {"repository": REPO, "feedback_id": prepared["feedback_id"], "issues_url": ISSUES_URL}
    if not gh:
        return {**base, "status": "unavailable", "submitted": False, "reason": "未找到GitHub CLI；可用宿主已连接的GitHub工具，或保留草稿和反馈链接。"}
    try:
        identity = api(gh, "user", runner)
        actor = identity.get("login", "") if isinstance(identity, dict) else ""
        if not isinstance(actor, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", actor):
            raise GitHubFailure("未取得已授权用户身份。")
    except (GitHubFailure, ValueError, OSError, subprocess.TimeoutExpired):
        return {**base, "status": "unavailable", "submitted": False, "reason": "未取得可用GitHub授权或无法访问GitHub，本次未创建反馈。"}
    actor_id = hashlib.sha256(actor.lower().encode()).hexdigest()[:8]
    receipt_path = receipt_path or payload_path.with_name(payload_path.stem + f".receipt-{actor_id}-{prepared['feedback_id'][:16]}.json")
    state = {"repository": REPO, "actor": actor, "feedback_id": prepared["feedback_id"]}
    previous = None
    try:
        if receipt_path.exists():
            previous = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not isinstance(previous, dict) or any(previous.get(key) != value for key, value in state.items()):
                raise ValueError("回执不属于当前反馈或账号。")
    except (OSError, ValueError):
        return {**base, "status": "unavailable", "submitted": False, "reason": "已有回执无法核对或属于另一份反馈；保留原回执，本次不创建。"}

    def unknown(reason: str) -> dict:
        data = {**(previous or {}), **state, "status": "submission_unknown", "submitted": None}
        try:
            store_receipt(receipt_path, data)
        except OSError:
            pass
        return {**base, "status": "submission_unknown", "submitted": None, "reason": reason,
                "receipt_path": str(receipt_path), "retry_create": False}

    def confirmed(issue: dict, status: str, created) -> dict:
        data = {**state, "status": "submitted", "submitted": True,
                "issue_url": issue["html_url"], "issue_number": issue["number"]}
        saved = True
        try:
            store_receipt(receipt_path, data)
        except OSError:
            saved = False
        return {**base, **data, "status": status, "created": created,
                "receipt_saved": saved, "receipt_path": str(receipt_path)}

    if previous and previous.get("issue_number"):
        try:
            issue = api(gh, f"repos/{REPO}/issues/{int(previous['issue_number'])}", runner)
            if valid_issue(issue, actor, prepared["marker"]):
                return confirmed(issue, "already_submitted", False)
        except (GitHubFailure, ValueError, TypeError, OSError, subprocess.TimeoutExpired):
            pass
    try:
        existing = find_existing(gh, actor, prepared["marker"], runner)
    except (GitHubFailure, ValueError, OSError, subprocess.TimeoutExpired):
        if previous:
            return unknown("无法核对此前提交结果；不要直接重建，先检查已有反馈。")
        return {**base, "status": "unavailable", "submitted": False, "reason": "无法检查已有反馈，本次未发起创建。"}
    if existing:
        return confirmed(existing, "already_submitted", False)
    if previous and previous.get("status") != "not_submitted":
        return unknown("此前有提交尝试但结果仍未确认；本次只查结果，不再次创建。")
    rejected_status = None
    try:
        store_receipt(receipt_path, {**state, "status": "submitting", "submitted": None})
    except OSError:
        return {**base, "status": "unavailable", "submitted": False, "reason": "无法保存本地提交回执，本次未创建反馈。"}
    output = ""
    try:
        with tempfile.TemporaryDirectory(prefix="shu-feedback-") as folder:
            body_file = Path(folder) / "body.md"
            body_file.write_text(prepared["issue_body"], encoding="utf-8")
            output = gh_call(gh, ["issue", "create", "--repo", "github.com/" + REPO,
                                  "--title", prepared["issue_title"], "--body-file", str(body_file)], runner, timeout=30)
    except GitHubFailure as exc:
        rejected_status = exc.http_status
    except (ValueError, OSError, subprocess.TimeoutExpired):
        pass
    match = re.search(re.escape(ISSUES_URL) + r"/(\d+)\b", output)
    if match:
        try:
            issue = api(gh, f"repos/{REPO}/issues/{match.group(1)}", runner)
            if valid_issue(issue, actor, prepared["marker"]):
                return confirmed(issue, "submitted", True)
        except (GitHubFailure, ValueError, OSError, subprocess.TimeoutExpired):
            pass
    try:
        existing = find_existing(gh, actor, prepared["marker"], runner)
        if existing:
            return confirmed(existing, "submitted", None)
        if rejected_status:
            data = {**state, "status": "not_submitted", "submitted": False}
            store_receipt(receipt_path, data)
            return {**base, **data, "reason": f"GitHub明确拒绝创建（HTTP {rejected_status}）；本次未提交，请先修复授权或校验问题。", "receipt_path": str(receipt_path)}
    except (GitHubFailure, ValueError, OSError, subprocess.TimeoutExpired):
        pass
    return unknown("创建已尝试，但GitHub结果未确认；请检查现有Issue，不自动重试创建。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True, help="宿主整理的结构化脱敏JSON，保存在授权的本地目录")
    parser.add_argument("--submit", action="store_true", help="仅在用户明确要求提交反馈后使用；默认只预览")
    parser.add_argument("--receipt", type=Path, help="可选本地回执路径，不放共享知识库")
    parser.add_argument("--channel", choices=("feishu-form", "github"), default="feishu-form",
                        help="默认准备免登录飞书表单字段；github为可选公开渠道，需已有授权")
    args = parser.parse_args()
    try:
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        result = (submit_github_feedback(payload, args.payload, submit=args.submit, receipt_path=args.receipt)
                  if args.channel == "github" else prepare_form_feedback(payload, submit=args.submit))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, "未提交反馈：" + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] in {"unavailable", "not_submitted", "browser_required"}:
        raise SystemExit(3)
    if result["status"] == "submission_unknown":
        raise SystemExit(4)


if __name__ == "__main__":
    main()
