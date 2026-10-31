#!/usr/bin/env python3
"""Read-only, offline evidence search. Python standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

SKILL_ROOT = Path(__file__).resolve().parents[1]
DATA = SKILL_ROOT / "references/knowledge/documents.jsonl"
MANIFEST = SKILL_ROOT / "references/knowledge/manifest.json"
CHECKLISTS = SKILL_ROOT / "references/knowledge/checklists.json"
REPORTED_PRACTICES = SKILL_ROOT / "references/knowledge/reported-practices.json"
FEEDBACK_TEMPLATE = SKILL_ROOT / "assets/反馈模板.txt"
FEEDBACK_CONFIG = SKILL_ROOT / "references/knowledge/feedback-config.json"
ISSUES_URL = "https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/issues"
STOP = {"报销", "材料", "什么", "哪些", "需要", "如何", "怎么", "办理", "一下", "查询", "上海", "大学"}
EXPANSIONS = (
    (r"版面|发表|出版", "版面费 出版费 审稿费 录用通知"),
    (r"咨询|专家", "专家咨询费 专家咨询意见表"),
    (r"出差|差旅|参会", "国内差旅 出差审批 结算单"),
    (r"办公|耗材|材料费|设备", "资产采购 入库 报销指南"),
    (r"测试|化验|加工", "测试化验加工费 清单 合同"),
    (r"劳务|临聘", "劳务费 支取表 申报"),
)


def load_documents(path: Path = DATA) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    for block in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(block[i:i+2] for i in range(max(0, len(block)-1)))
    return [term for term in tokens if term not in STOP]


def query_tokens(query: str) -> tuple[list[str], list[str]]:
    original = list(dict.fromkeys(tokenize(query)))
    expanded = query
    for pattern, words in EXPANSIONS:
        if re.search(pattern, query):
            expanded += " " + words
    return original, list(dict.fromkeys(tokenize(expanded)))


def passage(text: str, query: str, limit: int = 900) -> str:
    terms = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", query.lower()) + tokenize(query)
    positions = [text.lower().find(term) for term in terms if term not in STOP]
    positions = [pos for pos in positions if pos >= 0]
    start = max(0, min(positions, default=0) - limit // 4)
    return ("…" if start else "") + text[start:start+limit] + ("…" if len(text) > start+limit else "")


def search_documents(documents: list[dict], query: str, limit: int = 5, text_only: bool = False) -> list[dict]:
    original, terms = query_tokens(query)
    if not original:
        return []
    counters = [Counter(tokenize(doc["title"] * 4 + " " + doc.get("text", ""))) for doc in documents]
    freq = Counter(term for counter in counters for term in counter)
    lengths = [sum(counter.values()) for counter in counters]
    avg = sum(lengths) / max(1, len(lengths)) or 1
    ranked = []
    for doc, counter, length in zip(documents, counters, lengths):
        if text_only and doc["availability"] not in {"text_available", "partial_text"}:
            continue
        matched = [term for term in original if term in counter]
        if not matched or len(matched) / len(original) < 0.15:
            continue
        score = 0.0
        for term in terms:
            count = counter.get(term, 0)
            if count:
                idf = math.log(1 + (len(documents)-freq[term]+0.5)/(freq[term]+0.5))
                score += (1 if term in original else 0.18) * idf * count*2.5/(count+1.5*(0.25+0.75*length/avg))
        score *= 0.5 + len(matched) / len(original)
        if query.lower() in doc["title"].lower():
            score *= 2
        if doc.get("category") == "guide":
            score *= 1.2
        if doc["availability"] != "text_available":
            score *= 0.7
        ranked.append((score, doc, matched))
    ranked.sort(key=lambda row: (-row[0], row[1]["id"]))
    result, seen = [], set()
    for _, doc, matched in ranked:
        key = hashlib.sha256(doc.get("text", "").encode()).hexdigest() if doc.get("text") else doc["url"]
        if key in seen:
            continue
        seen.add(key)
        result.append({field: doc.get(field, "") for field in ("id", "title", "url", "published_date", "fetched_at", "availability", "effectivity", "category", "text_quality", "extraction_method")})
        result[-1].update(excerpt=passage(doc.get("text", ""), query), matched_terms=matched)
        if doc.get("related_official_sources"):
            result[-1]["related_official_sources"] = doc["related_official_sources"]
        if len(result) >= limit:
            break
    return result


def load_checklists(path: Path = CHECKLISTS) -> dict:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if bundle.get("schema_version") != 1:
        raise ValueError("不支持的常用清单版本。")
    return bundle


def reported_practices(query: str = "", template_id: str = "", path: Path = REPORTED_PRACTICES) -> list[dict]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if bundle.get("schema_version") != 1:
        raise ValueError("不支持的用户执行口径版本。")
    query = query.strip().lower()
    result = []
    for entry in bundle["entries"]:
        matches = template_id in entry["related_template_ids"] if template_id else (
            not query or any(query == keyword.lower() or (len(keyword) > 1 and keyword.lower() in query)
                             for keyword in entry["keywords"]))
        if matches:
            result.append(entry)
    return result


def print_reported_practices(entries: list[dict]) -> None:
    for entry in entries:
        print(f"\n【用户提供的学院执行口径；书面依据未核验】{entry['title']}")
        print(f"范围：{entry['scope']}\n记录日期：{entry['reported_on']}\n{entry['summary']}")
        for item in entry.get("materials", []):
            kind = "视情况补充" if item["kind"] == "conditional" else "按本口径准备"
            print(f"[{kind}] {item['name']}：{item['check']}\n适用条件：{item['when']}")
        for conflict in entry["conflicts"]:
            print("书面资料差异：" + conflict["description"])
        print("使用方式：" + entry["use_policy"])


def reviewed_checklist(template: dict, bundle: dict, documents: list[dict], today: date | None = None) -> dict:
    """Return material requirements only while their reviewed source snapshots match."""
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    by_id = {doc["id"]: doc for doc in documents}
    references, issues = [], []
    for item in template["materials"]:
        if not item.get("basis"):
            issues.append(f"材料项没有来源依据：{item['name']}")
    keys = list(dict.fromkeys(key for item in template["materials"] for key in item.get("basis", [])))
    if not keys:
        issues.append("清单没有已核对的来源。")
    for key in keys:
        review = bundle["source_reviews"].get(key)
        if review is None:
            issues.append(f"来源核对记录缺失：{key}")
            continue
        if review.get("status") != "reviewed":
            issues.append(f"该来源已被标记需复核：{key}")
        if not all(review.get(field) for field in ("locator", "method", "verified_summary")):
            issues.append(f"来源核对证据不完整：{key}")
        doc = by_id.get(review["source_id"])
        if doc is None:
            issues.append(f"知识源缺失：{review['source_id']}")
            continue
        references.append({**review, "review_id": key, "title": doc["title"], "url": doc["url"]})
        if doc.get("availability") != "text_available":
            issues.append(f"来源正文不完整：{doc['title']}")
        if hashlib.sha256(doc.get("text", "").encode()).hexdigest() != review["text_sha256"]:
            issues.append(f"来源内容已变：{doc['title']}")
        if date.fromisoformat(review["checked_on"]) > today:
            issues.append(f"核对日期晚于当前日期：{key}")
        if today >= date.fromisoformat(review["review_after"]):
            issues.append(f"已到复核日期：{key}（{review['review_after']}）")
    issues = list(dict.fromkeys(issues))
    result = {**template, "source_state": "needs_review" if issues else "reviewed_snapshot",
              "refresh_before_use": bool(issues), "context_match_required": True,
              "common_context": bundle["policy"]["common_context"],
              "references": references, "review_issues": issues}
    practices = reported_practices(template_id=template["id"])
    if practices:
        result["reported_practices"] = practices
        result["reported_practices_notice"] = "以下为用户提供的学院执行口径，未升级为已核验官方规则；先匹配学院、物品及经费，并说明书面资料差异。"
    if issues:
        result.pop("materials", None)
    return result


def checklist_result(query: str = "", bundle: dict | None = None, documents: list[dict] | None = None,
                     today: date | None = None) -> dict:
    bundle = bundle if bundle is not None else load_checklists()
    documents = documents if documents is not None else load_documents()
    exact = [item for item in bundle["templates"] if item["id"] == query]
    matches = exact or [item for item in bundle["templates"]
                        if not query or query in item["aliases"] or query == item["scenario_id"]]
    practices = reported_practices(query) if query else []
    if not matches and practices:
        related = {key for entry in practices for key in entry["related_template_ids"]}
        matches = [item for item in bundle["templates"] if item["id"] in related]
    if not matches:
        raise ValueError("没有对应的已维护清单；请先列出清单或按场景路由查原文，不套用相近事项。")
    notice = ("可复用的是已核对版本摘要，先匹配适用范围与事实；基础材料也以业务阶段和实际发生为条件。"
              "未知条件先确认，无法读取不判缺失；清单不代表规则现行有效、审批通过或已收齐所有材料。")
    if query and len(matches) == 1:
        return {"checklist": reviewed_checklist(matches[0], bundle, documents, today), "notice": notice}
    catalog = []
    for item in matches:
        state = reviewed_checklist(item, bundle, documents, today)
        catalog.append({key: state[key] for key in ("id", "title", "scope", "context_questions", "source_state", "review_issues")})
    return {"checklists": catalog, "selection_required": True, "reported_practices": practices,
            "notice": "请选择适用清单；多个分支不自动替你选择经费、币种或办理渠道。" + notice}


def feedback_info(checklist_id: str = "") -> dict:
    """Prepare a public feedback link from fixed fields and public metadata only."""
    title = "[反馈] 请补充问题概述"
    body = FEEDBACK_TEMPLATE.read_text(encoding="utf-8")
    if checklist_id:
        template = next((item for item in load_checklists()["templates"] if item["id"] == checklist_id), None)
        if template is None:
            raise ValueError("未知清单ID；反馈链接仅接受已维护的公开清单，不接受个人材料或自由正文。")
        title = "[反馈] " + template["title"]
        body = body.replace("关联清单/页面：", f"关联清单/页面：{checklist_id} / {template['title']}")
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["skill_version"]
    body = body.replace("Skill/资料包版本：", f"Skill/资料包版本（本地工具为{version}，出错时版本不同请另填）：")
    config = json.loads(FEEDBACK_CONFIG.read_text(encoding="utf-8"))
    return {"feedback_url": config["form_url"],
            "github_draft_url": ISSUES_URL + "/new?" + urlencode({"title": title, "body": body}),
            "choose_url": ISSUES_URL + "/new/choose", "issues_url": ISSUES_URL,
            "requires_github_account": False, "requires_account": config["requires_account"],
            "visibility": config["visibility"], "anonymous": config["anonymous"], "submitted": False,
            "api": config["api"], "channel_verification": config["verification"],
            "automatic_upload": False, "draft_template": body,
            "mode": "draft_only", "authorized_submission_supported": True,
            "submission_helper": "scripts/submit_feedback.py",
            "submission_example": "assets/反馈提交示例.json",
            "submission_requirements": ["用户明确请求提交反馈", "宿主已完成脱敏检查", "宿主具有可操作表单的浏览器工具；否则给使用者免登录链接"],
            "notice": "本命令只准备入口与草稿，不上传。首选飞书免登录匿名表单，内容由维护者查看；API尚未开通，不能向表单链接直接POST。用户明确要求后，有浏览器能力的宿主可代填并核对成功页；无浏览器能力则保留草稿及表单链接。GitHub是可选公开渠道。"}


def status() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = hashlib.sha256(DATA.read_bytes()).hexdigest()
    return {**manifest, "integrity_ok": actual == manifest["documents_sha256"],
            "checklists_integrity_ok": hashlib.sha256(CHECKLISTS.read_bytes()).hexdigest() == manifest.get("checklists_sha256"),
            "reported_practices_integrity_ok": hashlib.sha256(REPORTED_PRACTICES.read_bytes()).hexdigest() == manifest.get("reported_practices_sha256"),
            "notice": "快照时间不等于规则生效或逐条核验时间；请核对官方后续文件。"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("search", help="查找证据；结果本身不是合规结论")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5, choices=range(1, 21), metavar="1..20")
    find.add_argument("--text-only", action="store_true")
    read = commands.add_parser("read", help="读取原文及附件入口")
    read.add_argument("id")
    read.add_argument("--query", default="")
    state = commands.add_parser("status", help="查看快照时间、覆盖和完整性")
    checklist = commands.add_parser("checklist", help="复用有来源与核对日期的常用材料清单；无参数列出可选分支")
    checklist.add_argument("id", nargs="?", default="", help="清单ID、明确别名或场景ID")
    practice = commands.add_parser("practice", help="读取用户提供的学院执行口径，与官方原文分开")
    practice.add_argument("query", nargs="?", default="")
    feedback = commands.add_parser("feedback", help="生成脱敏反馈入口及空白草稿，不自动提交")
    feedback.add_argument("--checklist", default="", metavar="ID", help="仅预填公开清单ID、名称和版本")
    for command in (find, read, state, checklist, practice, feedback):
        command.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = status()
        elif args.command == "checklist":
            result = checklist_result(args.id)
        elif args.command == "practice":
            result = {"reported_practices": reported_practices(args.query),
                      "notice": "用户提供的学院执行口径；并非已核验官方规则，使用时说明范围、来源及书面资料差异。"}
        elif args.command == "feedback":
            result = feedback_info(args.checklist)
        elif args.command == "search":
            result = {"query": args.query, "hits": search_documents(load_documents(), args.query, args.limit, args.text_only),
                      "reported_practices": reported_practices(args.query),
                      "notice": "请 read 命中文档后作出判断。未取得正文的条目只证明存在入口。"}
        else:
            doc = next((doc for doc in load_documents() if doc["id"] == args.id), None)
            if doc is None:
                parser.exit(2, "没有这个文档 ID，请先 search。\n")
            result = dict(doc)
            if args.query:
                result["text"] = passage(doc.get("text", ""), args.query, 5000)
                result["excerpt_only"] = True
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "feedback":
            print(result["notice"] + "\n" + result["feedback_url"] + "\n\n" + result["draft_template"])
        elif args.command == "practice":
            print(result["notice"])
            print_reported_practices(result["reported_practices"])
        elif args.command == "checklist":
            print(result["notice"])
            if "checklists" in result:
                print_reported_practices(result.get("reported_practices", []))
                for entry in result["checklists"]:
                    print(f"\n{entry['id']}：{entry['title']} [{entry['source_state']}]\n适用：{entry['scope']}")
            else:
                entry = result["checklist"]
                print_reported_practices(entry.get("reported_practices", []))
                print(f"\n{entry['title']} [{entry['source_state']}]\n适用：{entry['scope']}")
                for question in entry["context_questions"]:
                    print("先匹配：" + question)
                for issue in entry["review_issues"]:
                    print("需复核：" + issue)
                for item in entry.get("materials", []):
                    kind = {"base": "基础", "conditional": "条件成立才需", "confirmation": "先确认"}[item["kind"]]
                    print(f"\n[{kind}] {item['name']}\n条件：{item['when']}\n核对：{item['check']}")
                for reference in entry["references"]:
                    print(f"\n依据：{reference['title']} · {reference['locator']}\n{reference['url']}\n核对：{reference['checked_on']}；复核提醒：{reference['review_after']}")
        elif args.command == "search":
            print(result["notice"])
            print_reported_practices(result.get("reported_practices", []))
            if not result["hits"]:
                print("未找到可用线索；请换词或补充官方资料，不据此断言可以或不可以报销。")
            for hit in result["hits"]:
                warning = "；扫描件机器识别未逐页核验，关键数字和条件须对照原件" if hit.get("text_quality") == "ocr_unverified" else ""
                print(f"\n[{hit['id']}] {hit['title']}\n{hit['url']}\n状态：{hit['availability']}；快照：{hit['fetched_at']}{warning}\n{hit['excerpt']}")
        elif args.command == "read":
            warning = "\n注意：扫描件机器识别未逐页核验，关键数字和条件须对照原件。" if result.get("text_quality") == "ocr_unverified" else ""
            print(f"{result['title']}\n{result['url']}\n状态：{result['availability']}；生效状态：{result['effectivity']}\n快照：{result['fetched_at']}{warning}\n\n{result['text']}")
            for item in result.get("attachments", []):
                print(f"附件：{item['title']} {item['url']}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"知识库读取失败：{exc}\n")


if __name__ == "__main__":
    main()
