#!/usr/bin/env python3
"""Read-only, offline evidence search. Python standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
DATA = SKILL_ROOT / "references/knowledge/documents.jsonl"
MANIFEST = SKILL_ROOT / "references/knowledge/manifest.json"
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
        if text_only and doc["availability"] != "text_available":
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
        result.append({field: doc.get(field, "") for field in ("id", "title", "url", "published_date", "fetched_at", "availability", "effectivity", "category")})
        result[-1].update(excerpt=passage(doc.get("text", ""), query), matched_terms=matched)
        if len(result) >= limit:
            break
    return result


def status() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = hashlib.sha256(DATA.read_bytes()).hexdigest()
    return {**manifest, "integrity_ok": actual == manifest["documents_sha256"],
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
    for command in (find, read, state):
        command.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = status()
        elif args.command == "search":
            result = {"query": args.query, "hits": search_documents(load_documents(), args.query, args.limit, args.text_only),
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
        elif args.command == "search":
            print(result["notice"])
            if not result["hits"]:
                print("未找到可用线索；请换词或补充官方资料，不据此断言可以或不可以报销。")
            for hit in result["hits"]:
                print(f"\n[{hit['id']}] {hit['title']}\n{hit['url']}\n状态：{hit['availability']}；快照：{hit['fetched_at']}\n{hit['excerpt']}")
        elif args.command == "read":
            print(f"{result['title']}\n{result['url']}\n状态：{result['availability']}；生效状态：{result['effectivity']}\n快照：{result['fetched_at']}\n\n{result['text']}")
            for item in result.get("attachments", []):
                print(f"附件：{item['title']} {item['url']}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"知识库读取失败：{exc}\n")


if __name__ == "__main__":
    main()
