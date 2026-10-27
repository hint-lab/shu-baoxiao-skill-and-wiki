#!/usr/bin/env python3
"""Render MinerU structured content as safe, page-labelled Markdown."""
from __future__ import annotations

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path


def escape_text(value: str) -> str:
    value = html.escape(value, quote=False).replace("\\", "\\\\")
    return re.sub(r"([\[\]_*`#])", r"\\\1", value)


class SafeTable(HTMLParser):
    allowed = {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0
        self.omitted = False

    def handle_starttag(self, name: str, attrs: list[tuple[str, str | None]]) -> None:
        name = name.lower()
        if name in {"script", "style", "iframe", "object"}:
            self.omitted = True
            self.suppressed += 1
            return
        if self.suppressed:
            return
        if name not in self.allowed:
            self.omitted = True
            if name in {"img", "svg"}:
                self.parts.append("[表格中的图像未公开，请查看原件]")
            return
        safe = []
        if name in {"td", "th"}:
            for key, value in attrs:
                if key in {"rowspan", "colspan"} and value and value.isdigit() and 1 <= int(value) <= 100:
                    safe.append(f' {key}="{int(value)}"')
        self.parts.append("<" + name + "".join(safe) + ">")

    def handle_endtag(self, name: str) -> None:
        name = name.lower()
        if name in {"script", "style", "iframe", "object"}:
            self.suppressed = max(0, self.suppressed - 1)
        elif not self.suppressed and name in self.allowed and name != "br":
            self.parts.append("</" + name + ">")

    def handle_data(self, data: str) -> None:
        if not self.suppressed:
            self.parts.append(html.escape(data, quote=False))


def table_content(value: str) -> tuple[str, bool]:
    if re.search(r"<table\b", value, re.I):
        parser = SafeTable()
        parser.feed(value)
        return "".join(parser.parts), parser.omitted
    # Table pipes remain Markdown syntax; arbitrary HTML remains literal text.
    return html.escape(value, quote=False), False


def render(payload: dict, page_map: list[int] | None = None) -> dict:
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("MinerU 输出没有页面。")
    if page_map is not None and len(pages) != len(page_map):
        raise ValueError("输出页数与原件页码映射不一致。")
    result, warnings = [], set()
    for index, page in enumerate(pages):
        number = page_map[index] if page_map is not None else int(page.get("page_idx", index)) + 1
        result.append(f"### 原件第 {number} 页")
        for block in page.get("blocks", []):
            kind = block.get("type", "")
            value = block.get("content", "")
            if kind == "page_number":
                continue
            if kind in {"image", "seal", "figure"}:
                result.append("[原件含图像或印章，未公开；请查看原页。]")
                warnings.add("images_omitted")
                continue
            if not isinstance(value, str):
                warnings.add("nontext_block_needs_review")
                continue
            value = value.strip()
            if not value:
                continue
            if kind == "table":
                for caption in block.get("captions") or []:
                    text = caption if isinstance(caption, str) else caption.get("content") if isinstance(caption, dict) else None
                    if isinstance(text, str) and text.strip():
                        result.append(escape_text(text.strip()))
                    elif text is not None or not isinstance(caption, str):
                        warnings.add("table_caption_needs_review")
                table, omitted = table_content(value)
                result.append(table)
                if omitted:
                    warnings.add("table_elements_omitted")
                for note in block.get("footnotes") or []:
                    text = note if isinstance(note, str) else note.get("content") if isinstance(note, dict) else None
                    if isinstance(text, str) and text.strip():
                        result.append(escape_text(text.strip()))
                    elif text is not None or not isinstance(note, str):
                        warnings.add("table_note_needs_review")
            elif kind in {"doc_title", "paragraph_title"}:
                result.append("#### " + escape_text(value))
            else:
                if kind not in {"text", "paragraph", "list", "equation", "header", "footer", "code"}:
                    warnings.add("unknown_block_type")
                result.append(escape_text(value))
    return {"markdown": "\n\n".join(result).strip() + "\n", "warnings": sorted(warnings), "pages": len(pages)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = render(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result["markdown"], encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "markdown"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
