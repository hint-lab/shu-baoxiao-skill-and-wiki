#!/usr/bin/env python3
"""Filter OCR blocks overlapping embedded screenshots; output is explicitly partial.

The pdftohtml XML layout and MinerU pages must come from the same original PDF.
This is an aid to human privacy review, not proof that all personal data is gone.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
import mineru_markdown


def redact(text: str) -> str:
    for pattern, replacement in [
        (r'(?<!\d)1[3-9]\d{9}(?!\d)', '[手机号已隐去]'),
        (r'(?<!\d)\d{8,19}(?!\d)', '[长数字已隐去]'),
        (r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[邮箱已隐去]'),
        (r'(?<![A-Za-z0-9])[A-Za-z]\d{8,}(?!\d)', '[示例编号已隐去]'),
        (r'((?:姓名|报销人|申请人|收款人|经办人|联系人)\s*[:：]\s*)[\u4e00-\u9fff]{2,4}', r'\1[姓名已隐去]'),
    ]:
        text = re.sub(pattern, replacement, text)
    return text


def sanitize(pages: dict[int, dict], layout_path: Path) -> dict:
    layouts = {int(x.attrib['number']): x for x in ET.parse(layout_path).getroot().findall('page')}
    if not pages or set(layouts) != set(pages):
        raise ValueError('PDF 版面与识别结果页码不一致。')
    output, region_pages, warnings, removed = [], [], set(), 0
    for n, page in sorted(pages.items()):
        layout = layouts[n]
        w, h = float(layout.attrib['width']), float(layout.attrib['height'])
        if w <= 0 or h <= 0:
            raise ValueError('PDF 页面尺寸无效。')
        images = []
        for element in layout.findall('image'):
            a = element.attrib
            x, y, iw, ih = (float(a[k]) for k in ('left', 'top', 'width', 'height'))
            images.append((x / w, y / h, (x + iw) / w, (y + ih) / h))
        if images:
            region_pages.append(n)
        kept = []
        for original in page.get('blocks', []):
            if original.get('type') in {'image', 'seal', 'figure', 'chart'}:
                continue
            bbox = original.get('bbox')
            if not isinstance(bbox, list) or len(bbox) != 4:
                removed += 1
                warnings.add('block_position_missing')
                continue
            x1, y1, x2, y2 = bbox
            area = max((x2 - x1) * (y2 - y1), 0.000001)
            overlap = any(max(0, min(x2, ix2) - max(x1, ix1)) *
                          max(0, min(y2, iy2) - max(y1, iy1)) / area > .05
                          for ix1, iy1, ix2, iy2 in images)
            if overlap:
                removed += 1
                continue
            block = dict(original)
            if isinstance(block.get('content'), str):
                block['content'] = redact(block['content'])
            # Captions and footnotes can also carry sensitive text.
            for key in ('captions', 'footnotes'):
                if key in block:
                    block[key] = [redact(x) if isinstance(x, str) else
                                  {**x, 'content': redact(x['content'])} if isinstance(x, dict) and isinstance(x.get('content'), str)
                                  else x for x in block[key]]
            kept.append(block)
        result = mineru_markdown.render({'pages': [{'blocks': kept}]}, [n])
        warnings.update(result['warnings'])
        text = result['markdown']
        if images:
            text += '\n[原页截图或图像已隐去，相关界面信息待人工隐私复核。]\n'
        output.append(text)
    return {'markdown': '\n'.join(output), 'privacy_redacted_regions': region_pages,
            'removed_blocks': removed, 'warnings': sorted(warnings | {'screenshots_privacy_withheld'})}
