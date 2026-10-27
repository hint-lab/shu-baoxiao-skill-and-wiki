#!/usr/bin/env python3
"""Convert Word source structure into readable Markdown without calling a model."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
N = {"w": W, "r": R}


def tag(name: str) -> str:
    return "{" + W + "}" + name


def attr(node: ET.Element | None, key: str, default: str = "") -> str:
    return node.get(tag(key), default) if node is not None else default


def md_escape(text: str) -> str:
    text = html.escape(text, quote=False).replace("\\", "\\\\")
    return re.sub(r"([\[\]_*`#])", r"\\\1", text)


def chinese_number(number: int) -> str:
    digits = "零一二三四五六七八九"
    if 1 <= number <= 9:
        return digits[number]
    if 10 <= number <= 99:
        tens, ones = divmod(number, 10)
        return (digits[tens] if tens > 1 else "") + "十" + (digits[ones] if ones else "")
    return str(number)


def roman_number(number: int) -> str:
    if not 1 <= number <= 3999:
        return str(number)
    values = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
              (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    result = ""
    for value, glyph in values:
        count, number = divmod(number, value)
        result += glyph * count
    return result


class WordParser:
    def __init__(self, path: Path):
        self.path = path
        self.warnings: set[str] = set()
        self.tables = 0
        self.image_count = 0
        self.counters: dict[str, dict[int, int]] = {}
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 30 * 1024 * 1024:
                raise ValueError("Word 正文过大，未解析。")
            self.document = ET.fromstring(archive.read(info))
            self.styles = ET.fromstring(archive.read("word/styles.xml")) if "word/styles.xml" in archive.namelist() else None
            self.numbering = ET.fromstring(archive.read("word/numbering.xml")) if "word/numbering.xml" in archive.namelist() else None
            self.image_count = sum(name.startswith("word/media/") and not name.endswith("/") for name in archive.namelist())
            if any(name.startswith("word/embeddings/") for name in archive.namelist()):
                self.warnings.add("embedded_object_not_extracted")
        if self.image_count:
            self.warnings.add("images_not_extracted")
        self.levels, self.nums = self._numbering()
        self.heading_styles = self._heading_styles()

    def _heading_styles(self) -> dict[str, int]:
        result = {}
        if self.styles is None:
            return result
        for style in self.styles.findall("./w:style", N):
            style_id = attr(style, "styleId")
            label = attr(style.find("./w:name", N), "val")
            match = re.search(r"(?:heading|标题)\s*([1-6])", style_id + " " + label, re.I)
            outline = style.find("./w:pPr/w:outlineLvl", N)
            if match:
                result[style_id] = int(match.group(1))
            elif outline is not None and attr(outline, "val").isdigit():
                result[style_id] = min(6, int(attr(outline, "val")) + 1)
        return result

    def _numbering(self) -> tuple[dict, dict]:
        levels, nums = {}, {}
        if self.numbering is None:
            return levels, nums
        for abstract in self.numbering.findall("./w:abstractNum", N):
            abstract_id = attr(abstract, "abstractNumId")
            levels[abstract_id] = {}
            for lvl in abstract.findall("./w:lvl", N):
                level = int(attr(lvl, "ilvl", "0"))
                levels[abstract_id][level] = {
                    "format": attr(lvl.find("./w:numFmt", N), "val", "decimal"),
                    "template": attr(lvl.find("./w:lvlText", N), "val", "%" + str(level + 1) + "."),
                    "start": int(attr(lvl.find("./w:start", N), "val", "1")),
                }
        for num in self.numbering.findall("./w:num", N):
            num_id = attr(num, "numId")
            abstract = attr(num.find("./w:abstractNumId", N), "val")
            overrides = {}
            for over in num.findall("./w:lvlOverride", N):
                start = over.find("./w:startOverride", N)
                if start is not None:
                    overrides[int(attr(over, "ilvl", "0"))] = int(attr(start, "val", "1"))
                if over.find("./w:lvl", N) is not None:
                    self.warnings.add("custom_numbering_override_needs_review")
            nums[num_id] = {"abstract": abstract, "starts": overrides}
        return levels, nums

    def _list_prefix(self, paragraph: ET.Element) -> str:
        properties = paragraph.find("./w:pPr/w:numPr", N)
        if properties is None:
            return ""
        num_id = attr(properties.find("./w:numId", N), "val")
        level = int(attr(properties.find("./w:ilvl", N), "val", "0"))
        spec = self.nums.get(num_id)
        definition = self.levels.get(spec["abstract"], {}).get(level) if spec else None
        if not spec or not definition:
            self.warnings.add("numbering_definition_missing")
            return "[原文列表编号待核] "
        if definition["format"] == "bullet":
            return "• "
        supported = {"decimal", "decimalZero", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman",
                     "chineseCounting", "chineseCountingThousand", "japaneseCounting", "decimalEnclosedCircle"}
        state = self.counters.setdefault(num_id, {})
        start = spec["starts"].get(level, definition["start"])
        state[level] = state.get(level, start - 1) + 1
        for lower in list(state):
            if lower > level:
                del state[lower]
        if definition["format"] not in supported:
            self.warnings.add("unsupported_numbering_format")
            return "[原文列表编号待核] "

        def replacement(match: re.Match) -> str:
            index = int(match.group(1)) - 1
            value = state.get(index, 1)
            fmt = self.levels.get(spec["abstract"], {}).get(index, {}).get("format", "decimal")
            if fmt.startswith("chinese") or fmt == "japaneseCounting":
                return chinese_number(value)
            if fmt in {"lowerLetter", "upperLetter"} and 1 <= value <= 26:
                return chr((97 if fmt == "lowerLetter" else 65) + value - 1)
            if fmt in {"lowerRoman", "upperRoman"}:
                result = roman_number(value)
                return result.lower() if fmt == "lowerRoman" else result
            if fmt == "decimalEnclosedCircle" and 1 <= value <= 20:
                return chr(0x2460 + value - 1)
            return f"{value:02d}" if fmt == "decimalZero" else str(value)

        return re.sub(r"%([1-9])", replacement, definition["template"]) + " "

    def _plain(self, node: ET.Element) -> str:
        if node.tag == tag("ins"):
            self.warnings.add("inserted_revision_needs_review")
        if node.tag in {tag("del"), tag("moveFrom")}:
            self.warnings.add("deleted_revision_omitted")
            return ""
        if node.tag == tag("r"):
            hidden = node.find("./w:rPr/w:vanish", N)
            if hidden is not None and attr(hidden, "val", "true") not in {"0", "false", "off"}:
                self.warnings.add("hidden_text_omitted")
                return ""
        if node.tag in {"{" + M + "}oMath", "{" + M + "}oMathPara"}:
            self.warnings.add("formula_structure_needs_review")
            text = "".join(item.text or "" for item in node.iter("{" + M + "}t"))
            return text + "[公式结构请核对原件]"
        if node.tag in {tag("drawing"), tag("pict"), tag("object")}:
            self.warnings.add("images_or_objects_not_extracted")
            return "[图片或嵌入对象：请查看原件]"
        if node.tag in {tag("footnoteReference"), tag("endnoteReference")}:
            self.warnings.add("notes_not_extracted")
            return "[注释请查看原件]"
        if node.tag == tag("t"):
            return node.text or ""
        if node.tag == tag("tab"):
            return "\t"
        if node.tag in {tag("br"), tag("cr")}:
            return "\n"
        return "".join(self._plain(child) for child in node)

    def _paragraph(self, paragraph: ET.Element, in_cell: bool = False) -> str:
        text = self._plain(paragraph).strip()
        if not text:
            return ""
        if paragraph.find(".//w:hyperlink", N) is not None:
            self.warnings.add("hyperlink_destination_not_extracted")
        prefix = self._list_prefix(paragraph)
        if in_cell:
            return html.escape(prefix + text, quote=False).replace("\n", "<br>")
        style = attr(paragraph.find("./w:pPr/w:pStyle", N), "val")
        level = self.heading_styles.get(style)
        outline = paragraph.find("./w:pPr/w:outlineLvl", N)
        if level is None and outline is not None and attr(outline, "val").isdigit():
            level = min(6, int(attr(outline, "val")) + 1)
        content = md_escape(prefix + text).replace("\n", "  \n")
        if prefix and re.match(r"^\d+\.", content):
            content = re.sub(r"^(\d+)\.", r"\1\\.", content)
        return ("#" * min(6, level + 1) + " " if level else "") + content

    def _table(self, table: ET.Element, continuation: dict | None = None) -> tuple[str, dict]:
        self.tables += 1
        rendered_rows: list[list[dict]] = []
        active: dict[tuple[int, int], dict] = {}
        for row_index, tr in enumerate(table.findall("./w:tr", N)):
            row: list[dict] = []
            next_active: dict[tuple[int, int], dict] = {}
            before = int(attr(tr.find("./w:trPr/w:gridBefore", N), "val", "0"))
            col = before
            if before:
                row.append({"content": "", "colspan": before, "rowspan": 1})
            for tc in tr.findall("./w:tc", N):
                span = int(attr(tc.find("./w:tcPr/w:gridSpan", N), "val", "1"))
                merge = tc.find("./w:tcPr/w:vMerge", N)
                state = attr(merge, "val", "continue") if merge is not None else ""
                parts = []
                for child in tc:
                    if child.tag == tag("p"):
                        part = self._paragraph(child, in_cell=True)
                        if part:
                            parts.append(part)
                    elif child.tag == tag("tbl"):
                        parts.append(self._table(child)[0])
                content = "<br>".join(parts)
                key = (col, span)
                if state == "continue" and key in active:
                    cell = active[key]
                    cell["rowspan"] += 1
                    if content and content != cell["content"]:
                        cell["content"] += ("<br>" if cell["content"] else "") + content
                    next_active[key] = cell
                elif state == "continue" and row_index == 0 and continuation and key in continuation:
                    previous = continuation[key]
                    carried = "[接上表] " + previous["content"]
                    if content and content != previous["content"]:
                        carried += "<br>" + content
                    cell = {"content": carried, "colspan": span, "rowspan": 1}
                    row.append(cell)
                    next_active[key] = cell
                    self.warnings.add("cross_table_merge_continued")
                else:
                    if state == "continue":
                        self.warnings.add("unmatched_vertical_merge")
                    cell = {"content": content, "colspan": span, "rowspan": 1}
                    row.append(cell)
                    if state == "restart":
                        next_active[key] = cell
                col += span
            rendered_rows.append(row)
            active = next_active
        output = ["<table>", "<tbody>"]
        for row in rendered_rows:
            output.append("<tr>")
            for cell in row:
                columns = f' colspan="{cell["colspan"]}"' if cell["colspan"] > 1 else ""
                rows = f' rowspan="{cell["rowspan"]}"' if cell["rowspan"] > 1 else ""
                output.append(f'<td{columns}{rows}>{cell["content"]}</td>')
            output.append("</tr>")
        return "\n".join(output + ["</tbody>", "</table>"]), active

    def render(self) -> dict:
        body = self.document.find("./w:body", N)
        if body is None:
            raise ValueError("Word 文件缺少正文。")
        blocks = []

        def append(node: ET.Element) -> None:
            if node.tag == tag("p"):
                value = self._paragraph(node)
                if value:
                    blocks.append(value)
            elif node.tag == tag("tbl"):
                blocks.append(self._table(node)[0])
            elif node.tag in {tag("sdt"), tag("sdtContent"), tag("customXml")}:
                for child in node:
                    append(child)
            elif node.tag == tag("altChunk"):
                self.warnings.add("external_chunk_not_extracted")

        previous_table = {}
        adjacent = False
        for node in body:
            if node.tag == tag("tbl"):
                value, previous_table = self._table(node, continuation=previous_table if adjacent else None)
                blocks.append(value)
                adjacent = True
            else:
                append(node)
                adjacent = False
        return {"markdown": "\n\n".join(blocks).strip() + "\n", "warnings": sorted(self.warnings),
                "table_count": self.tables, "image_count": self.image_count}


def parse_word(path: Path) -> dict:
    path = path.expanduser().resolve()
    if path.suffix.lower() not in {".doc", ".docx"}:
        raise ValueError("仅支持 .doc 或 .docx。")
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    is_ooxml = False
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            is_ooxml = "word/document.xml" in archive.namelist()
    if path.suffix.lower() == ".docx" or is_ooxml:
        result = WordParser(path).render()
    else:
        executable = shutil.which("soffice") or shutil.which("libreoffice")
        if not executable:
            raise ValueError("旧版 .doc 需要 LibreOffice 转换；原件未修改。")
        with tempfile.TemporaryDirectory(prefix="shu-word-") as temp:
            root = Path(temp)
            profile = (root / "profile").as_uri()
            process = subprocess.run([executable, "--headless", "-env:UserInstallation=" + profile,
                                      "--convert-to", "docx", "--outdir", str(root), str(path)],
                                     capture_output=True, text=True, timeout=120)
            converted = root / (path.stem + ".docx")
            if process.returncode or not converted.is_file():
                raise ValueError("旧版 .doc 转换失败；原件未修改。")
            result = WordParser(converted).render()
            result["warnings"] = sorted(set(result["warnings"]) | {"legacy_doc_converted_with_libreoffice"})
    result.update(source_format=path.suffix.lower(), source_sha256=source_hash)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = parse_word(args.file)
        if args.output:
            if args.output.resolve() == args.file.resolve():
                raise ValueError("输出不能覆盖原件。")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result["markdown"], encoding="utf-8")
            print(json.dumps({key: value for key, value in result.items() if key != "markdown"}, ensure_ascii=False))
        elif args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["markdown"], end="")
            if result["warnings"]:
                import sys
                print("需核对：" + ", ".join(result["warnings"]), file=sys.stderr)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Word 解析失败：{exc}\n")


if __name__ == "__main__":
    main()
