from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
import json
import sys
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("word_markdown", ROOT / "skills/shu-baoxiao/scripts/word_to_markdown.py")
word = importlib.util.module_from_spec(spec)
spec.loader.exec_module(word)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def fixture(path: Path, body: str, numbering: str = "") -> None:
    document = f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        if numbering:
            archive.writestr("word/numbering.xml", numbering)


class WordMarkdownTests(unittest.TestCase):
    def test_table_merge_and_literal_content_preserved_without_repetition(self):
        body = '''<w:tbl><w:tblGrid><w:gridCol/><w:gridCol/><w:gridCol/></w:tblGrid>
        <w:tr><w:tc><w:tcPr><w:gridSpan w:val="3"/></w:tcPr><w:p><w:r><w:t>表格标题</w:t></w:r></w:p></w:tc></w:tr>
        <w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>用餐原因</w:t></w:r></w:p></w:tc>
        <w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>选项一</w:t></w:r></w:p></w:tc></w:tr>
        <w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc>
        <w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>&lt;script&gt;不能执行&lt;/script&gt;</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.docx"
            fixture(path, body)
            before = path.read_bytes()
            result = word.parse_word(path)
            self.assertEqual(path.read_bytes(), before)
        text = result["markdown"]
        self.assertIn('colspan="3"', text)
        self.assertIn('rowspan="2"', text)
        self.assertEqual(text.count("表格标题"), 1)
        self.assertEqual(text.count("用餐原因"), 1)
        self.assertIn("&lt;script&gt;不能执行&lt;/script&gt;", text)
        self.assertNotIn("<script>", text)

    def test_automatic_list_numbering_and_unmatched_merge_warning(self):
        numbering = f'''<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="1">
        <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="chineseCounting"/><w:lvlText w:val="%1、"/></w:lvl>
        </w:abstractNum><w:num w:numId="7"><w:abstractNumId w:val="1"/></w:num></w:numbering>'''
        para = lambda text: f'<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="7"/></w:numPr></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
        body = para("第一项") + para("第二项") + '<w:tbl><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p><w:r><w:t>孤立单元格</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "numbered.docx"
            fixture(path, body, numbering)
            result = word.parse_word(path)
        self.assertIn("一、 第一项", result["markdown"])
        self.assertIn("二、 第二项", result["markdown"])
        self.assertIn("孤立单元格", result["markdown"])
        self.assertIn("unmatched_vertical_merge", result["warnings"])

    def test_adjacent_tables_preserve_a_continued_vertical_label(self):
        body = '''<w:tbl><w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>接待费用</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:tbl><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc></w:tr>
        <w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc></w:tr></w:tbl>'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "split.docx"
            fixture(path, body)
            result = word.parse_word(path)
        self.assertEqual(result["table_count"], 2)
        self.assertIn("[接上表] 接待费用", result["markdown"])
        self.assertIn('rowspan="2"', result["markdown"])
        self.assertIn("cross_table_merge_continued", result["warnings"])
        self.assertNotIn("unmatched_vertical_merge", result["warnings"])

    def test_mineru_pages_and_html_tables_are_sanitized(self):
        spec = importlib.util.spec_from_file_location("mineru_markdown", ROOT / "tools/mineru_markdown.py")
        mineru = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mineru)
        payload = {"pages": [{"page_idx": 0, "blocks": [
            {"type": "text", "content": "条款 <不执行> **重点** <strong>说明</strong>"},
            {"type": "table", "content": '<table><tr><td rowspan="2" onclick="bad()">金额<script>bad()</script></td></tr></table>',
             "captions": [{"content": "表一标题"}], "footnotes": [{"content": "重要适用条件"}]},
            {"type": "image", "content": "data:image/png;base64,private"},
        ]}]}
        result = mineru.render(payload, page_map=[12])
        self.assertIn("原件第 12 页", result["markdown"])
        self.assertIn('rowspan="2"', result["markdown"])
        self.assertNotIn("onclick", result["markdown"])
        self.assertNotIn("<script>", result["markdown"])
        self.assertNotIn("data:image", result["markdown"])
        self.assertIn("images_omitted", result["warnings"])
        self.assertIn("表一标题", result["markdown"])
        self.assertIn("重要适用条件", result["markdown"])
        self.assertIn("**重点** 说明", result["markdown"])
        self.assertNotIn("&lt;strong&gt;", result["markdown"])

    def test_manual_screenshot_overlap_is_withheld_from_public_text(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import sanitize_manual
            payload = {1: {"blocks": [
                {"type": "text", "bbox": [0.1, 0.1, 0.8, 0.2], "content": "安全的流程说明"},
                {"type": "text", "bbox": [0.2, 0.4, 0.5, 0.5], "content": "截图中的私人字段"},
                {"type": "text", "bbox": [0.1, 0.8, 0.9, 0.9], "content": "联系电话：13812345678"},
            ]}}
            with tempfile.TemporaryDirectory() as folder:
                layout = Path(folder) / "layout.xml"
                layout.write_text('<pdf2xml><page number="1" width="100" height="100"><image left="15" top="35" width="50" height="25"/></page></pdf2xml>')
                result = sanitize_manual.sanitize(payload, layout)
            self.assertIn("安全的流程说明", result["markdown"])
            self.assertNotIn("截图中的私人字段", result["markdown"])
            self.assertNotIn("13812345678", result["markdown"])
            self.assertEqual(result["privacy_redacted_regions"], [1])
            self.assertEqual(result["removed_blocks"], 1)
        finally:
            sys.path.remove(str(ROOT / "tools"))

    def test_mineru_reuses_known_job_and_never_retries_uncertain_submission(self):
        spec = importlib.util.spec_from_file_location("mineru_p330", ROOT / "tools/mineru_p330.py")
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        calls = []
        markdown = b"# sample\n"
        structure = b'{"pages":[]}'

        def fake_call(host, container, operation, *, ident="", payload=None):
            calls.append(operation)
            if operation == "submit":
                return 202, json.dumps({"job_id": "job_123", "status": "queued"}).encode()
            if operation == "job":
                job = {"status": "completed", "files": [{"status": "completed", "output_files": {
                    "markdown": {"file_id": "md_1", "bytes": len(markdown)},
                    "structured_content": {"file_id": "json_1", "bytes": len(structure)},
                }}]}
                return 200, json.dumps(job).encode()
            return 200, markdown if ident == "md_1" else structure

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pdf = root / "sample.pdf"
            pdf.write_bytes(b"%PDF-1.4\nexample")
            with patch.object(client, "call", side_effect=fake_call):
                client.parse_pdf(pdf, root / "result", "test-host", "gateway", "basic", "all", 20)
                client.parse_pdf(pdf, root / "result", "test-host", "gateway", "basic", "all", 20)
                self.assertEqual(calls.count("submit"), 1)
                uncertain = root / "uncertain"
                uncertain.mkdir()
                (uncertain / "submission-uncertain.json").write_text("{}")
                with self.assertRaisesRegex(RuntimeError, "不要重复提交"):
                    client.parse_pdf(pdf, uncertain, "test-host", "gateway", "basic", "all", 20)
                self.assertEqual(calls.count("submit"), 1)


if __name__ == "__main__":
    unittest.main()
