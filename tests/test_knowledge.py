from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/shu-baoxiao"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


knowledge = module("knowledge", SKILL / "scripts/knowledge.py")
build = module("build", ROOT / "tools/build.py")
maintain = module("maintain", ROOT / "tools/maintain.py")


class KnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = knowledge.load_documents()

    def test_public_sources_and_no_local_runtime_data(self):
        self.assertEqual(len({doc["id"] for doc in self.docs}), len(self.docs))
        for doc in self.docs:
            self.assertEqual(urlparse(doc["url"]).netloc, "cwc.shu.edu.cn")
            self.assertEqual(doc["effectivity"], "unverified")
            self.assertNotIn("/Users/", json.dumps(doc, ensure_ascii=False))
            self.assertNotRegex(doc["title"], "退回名单|供应商|中标")
            for attachment in doc["attachments"]:
                self.assertEqual(urlparse(attachment["url"]).netloc, "cwc.shu.edu.cn")
        self.assertTrue(knowledge.status()["integrity_ok"])

    def test_retrieval_finds_relevant_originals(self):
        for query, source_id in [("版面费 外币", "a2b744cda8112604"), ("国内差旅", "974131a888750e5f"), ("专家咨询意见表", "265ba03d107d9a2e")]:
            hits = knowledge.search_documents(self.docs, query, 8)
            self.assertIn(source_id, [hit["id"] for hit in hits], query)
            self.assertTrue(all(hit["url"] and "availability" in hit for hit in hits))
        self.assertEqual(knowledge.search_documents(self.docs, "quantumxyz987654"), [])

    def test_entry_only_does_not_turn_into_evidence(self):
        entry = {"id": "x", "title": "专家咨询意见表", "url": "https://cwc.shu.edu.cn/x", "text": "", "availability": "entry_only"}
        self.assertEqual(knowledge.search_documents([entry], "专家咨询", text_only=True), [])
        self.assertEqual(knowledge.search_documents([entry], "专家咨询")[0]["availability"], "entry_only")

    def test_material_organization_covers_every_source_without_inventing_validity(self):
        index = build.organize_documents(self.docs, build.scenarios())
        records = {record["id"]: record for record in index["records"]}
        self.assertEqual(set(records), {doc["id"] for doc in self.docs})
        by_id = {doc["id"]: doc for doc in self.docs}
        for doc in self.docs:
            record = records[doc["id"]]
            self.assertIn(record["kind"], build.KINDS)
            if not record["needs_text"] and doc["availability"] != "text_available":
                self.assertEqual(doc["source_type"], "page")
                self.assertTrue(record["linked_readable"])
                self.assertEqual(len(doc["attachments"]), len(record["linked_readable"]))
                self.assertTrue(all(by_id[source_id]["availability"] == "text_available" for source_id in record["linked_readable"]))
        for scene in build.scenarios():
            for source_id in scene["source_ids"]:
                self.assertIn(scene["id"], records[source_id]["scenarios"])
        self.assertEqual(build.material_kind({"title": "上海大学专家咨询意见表2024版.rar"}), "form")
        self.assertEqual(build.material_kind({"title": "国内差旅费报销指南（2024版）"}), "guide")
        self.assertEqual(build.material_kind({"title": "上海大学智能报销操作手册"}), "manual")
        self.assertEqual(build.material_kind({"title": "科研经费管理办法"}), "policy")

    def test_duplicate_groups_compare_text_and_preserve_all_entries(self):
        index = build.organize_documents(self.docs, build.scenarios())
        by_id = {doc["id"]: doc for doc in self.docs}
        for group in index["same_extracted_text_groups"]:
            self.assertGreater(len(group), 1)
            self.assertEqual(len({re.sub(r"\s+", "", by_id[source_id]["text"]) for source_id in group}), 1)
        queue = build.material_reports(self.docs, build.scenarios(), index)[ROOT / "wiki/待补资料.md"]
        for item in index["records"]:
            self.assertEqual(f"/{item['id']}.md)" in queue, item["needs_text"])

    def test_ocr_uncertainty_reaches_search_and_source_pages(self):
        ocr = [doc for doc in self.docs if doc.get("text_quality") == "ocr_unverified"]
        self.assertTrue(ocr)
        doc = ocr[0]
        self.assertIn("机器识别未逐页核验", build.source_page(doc))
        hits = knowledge.search_documents([doc], doc["title"], limit=1)
        self.assertEqual(hits[0]["text_quality"], "ocr_unverified")

    def test_form_copies_match_metadata_and_do_not_expose_redacted_pages(self):
        assets = [doc for doc in self.docs if doc.get("public_asset")]
        self.assertGreaterEqual(len(assets), 1)
        for doc in assets:
            asset = doc["public_asset"]
            path = SKILL / asset["path"]
            self.assertTrue(path.is_relative_to(SKILL / "assets/forms"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["sha256"])
            self.assertIn("../../" + asset["path"].split("/")[0], build.source_page(doc))
        guide = next(doc for doc in self.docs if doc["id"] == "1e88716b10c71712")
        self.assertEqual(guide["privacy_redacted_pages"], [70, 71, 72, 73])
        self.assertEqual(guide["text"].count("该页涉及个人账户示例"), 4)

    def test_skill_runs_from_a_different_directory_without_repo(self):
        with tempfile.TemporaryDirectory(prefix="shu-skill-") as folder:
            destination = Path(folder) / "技能 带空格"
            shutil.copytree(SKILL, destination, ignore=shutil.ignore_patterns("__pycache__"))
            command = [sys.executable, str(destination / "scripts/knowledge.py"), "search", "外币 版面费", "--json"]
            output = subprocess.check_output(command, cwd=folder, text=True)
            hits = json.loads(output)["hits"]
            self.assertTrue(hits)
            read = subprocess.run([sys.executable, str(destination / "scripts/knowledge.py"), "read", "not-found"], cwd=folder, capture_output=True, text=True)
            self.assertEqual(read.returncode, 2)
            self.assertNotIn("Traceback", read.stderr)

    def test_generated_markdown_links_and_consistency(self):
        for path, expected in build.generated_files().items():
            self.assertEqual(path.read_text(encoding="utf-8"), expected, str(path))
        for path in list((ROOT / "wiki").glob("*.md")) + list(SKILL.rglob("*.md")):
            text = re.sub(r"`{3,}.*?`{3,}", "", path.read_text(encoding="utf-8"), flags=re.S)
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if not target.startswith(("http:", "https:", "#", "mailto:")):
                    self.assertTrue((path.parent / unquote(target.split("#")[0])).exists(), f"{path}: {target}")

    def test_portable_packages_include_data_and_not_user_state(self):
        with tempfile.TemporaryDirectory() as folder:
            packages = build.build_packages(Path(folder))
            for path in packages[:2]:
                with zipfile.ZipFile(path) as archive:
                    names = archive.namelist()
                    self.assertIn("shu-baoxiao/SKILL.md", names)
                    self.assertIn("shu-baoxiao/references/knowledge/documents.jsonl", names)
                    self.assertIn("shu-baoxiao/LICENSE", names)
                    self.assertFalse(any("__pycache__" in name or "data/settings" in name for name in names))
                    if "workbuddy" in path.name:
                        skill = archive.read("shu-baoxiao/SKILL.md").decode()
                        for key in ("display_name:", "display_name_en:", "description_zh:", "description_en:", "version:", "author:"):
                            self.assertIn(key, skill)
            chat = Path(folder) / "chat/publication.txt"
            self.assertIn("https://cwc.shu.edu.cn/info/1113/4276.htm", chat.read_text())
            consultation = (Path(folder) / "chat/consultation.txt").read_text()
            self.assertIn("上海大学专家咨询意见表2024版.rar", consultation)
            self.assertIn("【工作表：Sheet1】", consultation)

    def test_packages_are_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            first = build.build_packages(Path(folder) / "first")
            second = build.build_packages(Path(folder) / "second")
            self.assertEqual([p.read_bytes() for p in first], [p.read_bytes() for p in second])


class MaintenanceTests(unittest.TestCase):
    def test_markdown_import_allows_structured_tables_and_rejects_active_content(self):
        maintain.validate_markdown('## 标题\n\n<table><tr><td rowspan="2">金额</td></tr></table>')
        for bad in ('<script>alert(1)</script>', '<td onclick="bad()">数值</td>', '![私图](data:image/png;base64,abc)'):
            with self.assertRaises(ValueError):
                maintain.validate_markdown(bad)

    def test_only_public_official_urls(self):
        for bad in ("http://cwc.shu.edu.cn/x", "https://evil.example/x", "https://cwc.shu.edu.cn.evil.example/x", "https://user:pass@cwc.shu.edu.cn/x"):
            with self.assertRaises(ValueError):
                maintain.official_url(bad)

    def test_extract_article_without_navigation_and_keep_attachment(self):
        html = '''<html><head><title>报销指南-上海大学财务处</title></head><body><nav>错误导航不要索引</nav><div>创建时间：2026-10-27</div><div id="vsb_content"><p>真实业务要求及适用条件。</p><p>''' + "材料说明。"*20 + '''</p></div><a href="/system/_content/download.jsp?wbfileid=abc">空白表格</a></body></html>'''
        result = maintain.parse_page("https://cwc.shu.edu.cn/info/1/2.htm", html, "2026-10-27")
        self.assertEqual(result["title"], "报销指南")
        self.assertNotIn("错误导航", result["text"])
        self.assertEqual(result["availability"], "text_available")
        self.assertEqual(result["published_date"], "2026-10-27")
        self.assertEqual(len(result["attachments"]), 1)
        entry = maintain.parse_page("https://cwc.shu.edu.cn/x", "<title>只有入口</title><nav>" + "导航"*100 + "</nav>", "2026-10-27")
        self.assertEqual(entry["availability"], "entry_only")

    def test_updates_preserve_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sources.jsonl"
            path.write_text(json.dumps({"id": "original", "url": "https://cwc.shu.edu.cn/x"})+"\n")
            maintain.save({"id": "changed", "url": "https://cwc.shu.edu.cn/x", "text": "new"}, path)
            result = json.loads(path.read_text())
            self.assertEqual(result["id"], "original")
            self.assertEqual(result["text"], "new")


if __name__ == "__main__":
    unittest.main()
