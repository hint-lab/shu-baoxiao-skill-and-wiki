from __future__ import annotations

import importlib.util
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
SKILL = ROOT / "skills/shu-reimbursement"


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
                    self.assertIn("shu-reimbursement/SKILL.md", names)
                    self.assertIn("shu-reimbursement/references/knowledge/documents.jsonl", names)
                    self.assertIn("shu-reimbursement/LICENSE", names)
                    self.assertFalse(any("__pycache__" in name or "data/settings" in name for name in names))
                    if "workbuddy" in path.name:
                        skill = archive.read("shu-reimbursement/SKILL.md").decode()
                        for key in ("display_name:", "display_name_en:", "description_zh:", "description_en:", "version:", "author:"):
                            self.assertIn(key, skill)
            chat = Path(folder) / "chat/publication.txt"
            self.assertIn("https://cwc.shu.edu.cn/info/1113/4276.htm", chat.read_text())

    def test_packages_are_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            first = build.build_packages(Path(folder) / "first")
            second = build.build_packages(Path(folder) / "second")
            self.assertEqual([p.read_bytes() for p in first], [p.read_bytes() for p in second])


class MaintenanceTests(unittest.TestCase):
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
