#!/usr/bin/env python3
"""Read the school's consultation-tax XLSX into Markdown, without changing it."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

S = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def coordinate(address: str) -> tuple[int, int]:
    match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', address)
    if not match:
        raise ValueError('Invalid cell address')
    col = 0
    for char in match[1]:
        col = col * 26 + ord(char) - 64
    return int(match[2]), col


def bounds(address: str) -> tuple[int, int, int, int]:
    first, _, last = address.partition(':')
    r1, c1 = coordinate(first)
    r2, c2 = coordinate(last or first)
    return r1, c1, r2, c2


def read_workbook(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for item in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', S):
                shared.append(''.join(t.text or '' for t in item.findall('.//s:t', S)))
        rels = {x.attrib['Id']: x.attrib['Target'] for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        sheets = []
        for node in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', S):
            target = rels[node.attrib[R]]
            member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            root = ET.fromstring(z.read(member))
            cells, shared_formulas = {}, {}
            for cell in root.findall('s:sheetData/s:row/s:c', S):
                value = cell.find('s:v', S)
                value = value.text if value is not None else ''
                kind = cell.get('t')
                if kind == 's':
                    value = shared[int(value)]
                elif kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.findall('s:is//s:t', S))
                formula = cell.find('s:f', S)
                if formula is not None:
                    text = formula.text
                    if formula.get('t') == 'shared':
                        ident = formula.get('si')
                        if text:
                            shared_formulas[ident] = text
                        else:
                            original = shared_formulas.get(ident, '')
                            # This school workbook uses a single relative formula family.
                            if not re.fullmatch(r'A([0-9]+)-\(A\1-800\)\*0\.2', original):
                                raise ValueError('Shared formula changed; inspect before importing')
                            row, col = coordinate(cell.attrib['r'])
                            if col != 2:
                                raise ValueError('Shared formula moved to another column')
                            text = f'A{row}-(A{row}-800)*0.2'
                    elif formula.attrib:
                        raise ValueError('Formula layout changed; inspect before importing')
                    if not text:
                        raise ValueError('Formula text missing')
                    cells[cell.attrib['r']] = {'formula': '=' + text, 'cached': value or ''}
                elif value not in (None, ''):
                    cells[cell.attrib['r']] = {'value': value}
            sheets.append({'name': node.attrib['name'], 'state': node.get('state', 'visible'),
                           'cells': cells, 'merges': [x.attrib['ref'] for x in root.findall('s:mergeCells/s:mergeCell', S)]})
        return sheets


def convert(path: Path) -> dict:
    sheets = read_workbook(path)
    if [s['name'] for s in sheets] != ['专家咨询费税前对照表', 'Sheet2', 'Sheet3']:
        raise ValueError('Workbook sheets changed; review before importing')
    used = set()
    main, formulas, empty = sheets

    def value(sheet, address):
        cell = sheet['cells'].get(address, {})
        if cell:
            used.add((sheet['name'], address))
        return cell.get('value', '')

    def table(sheet, area):
        r1, c1, r2, c2 = bounds(area)
        anchors, covered = {}, set()
        for merged in sheet['merges']:
            a, b, c, d = bounds(merged)
            if c < r1 or a > r2 or d < c1 or b > c2:
                continue
            if not (r1 <= a <= c <= r2 and c1 <= b <= d <= c2):
                raise ValueError('A merge crosses a selected section')
            anchors[(a,b)] = (c-a+1, d-b+1)
            covered.update((r,k) for r in range(a,c+1) for k in range(b,d+1) if (r,k)!=(a,b))
        by_position = {coordinate(k): k for k in sheet['cells']}
        lines = ['<table>', '<tbody>']
        for r in range(r1,r2+1):
            lines.append('<tr>')
            for c in range(c1,c2+1):
                if (r,c) in covered:
                    continue
                rowspan, colspan = anchors.get((r,c),(1,1))
                attrs = (f' rowspan="{rowspan}"' if rowspan>1 else '') + (f' colspan="{colspan}"' if colspan>1 else '')
                address = by_position.get((r,c))
                text = value(sheet,address) if address else ''
                text = html.escape(str(text).strip()).replace('\n','<br>')
                lines.append(f'<td{attrs}>{text}</td>')
            lines.append('</tr>')
        return '\n'.join(lines+['</tbody>','</table>'])

    comparison = ['| 咨询专家（原表分组） | 咨询方式 | 时间/次数口径 | 税后原值 | 税前原文 |',
                  '| --- | --- | --- | --- | --- |']
    for group, rate_row, call_row in [('院士、知名专家',4,5), ('高级专业技术人员',7,8), ('其他人员',10,11)]:
        for after,before,title in [('D','J','半天'),('E','K','第1、2天'),('F','L','第3天以后')]:
            comparison.append(f'| {group} | 会议咨询 | {title} | {value(main,f"{after}{rate_row}").strip()} | {value(main,f"{before}{rate_row}").strip()} |')
        comparison.append(f'| {group} | 通信咨询 | 人/次（原表单元格口径） | {value(main,f"D{call_row}").strip()} | {value(main,f"J{call_row}").strip()} |')
    lines = ['## 整理说明', '',
             '以下按原工作簿的内容分区展示，保留原始文字、数值及表头合并关系；不是对现行标准或适用范围的重新认定。原件未标明的单位、限额措辞和人员归类不作补写。', '',
             '## 工作表：专家咨询费税前对照表', '',
             '### 纵向税前税后对照（整理视图）', '',
             '按原表视觉分组对应展示，便于比较。会议咨询的原表总表头为“元/人/天”，半天及通信口径按原列和单元格分别保留；下面另附原始单元格结构供核对。', '',
             '\n'.join(comparison), '',
             '### 纵向科研项目咨询标准（原表 B1:F11，税后）', '', table(main,'B1:F11'), '',
             '### 纵向科研项目咨询标准（原表 H1:L11，税前）', '', table(main,'H1:L11'), '',
             '原表两区之间的标记（G3:G11）：' + value(main,'G3').strip() + '。', '',
             '### 横向科研项目咨询标准（原表 B14:D20，税前）', '', table(main,'B14:D20'), '',
             '### 专家讲座费说明（原表 H14:L18，税前）', '']
    for r in range(14,19):
        lines.extend([value(main,f'H{r}').strip(), ''])
    lines.extend(['## 工作表：Sheet2', '',
                  '原工作表没有列标题。下列“原值”“公式”“缓存结果”是整理标签；B2:B16 的共享公式按 Excel 的相对引用展开。公式和缓存结果均取自原件，未重新计算，也不能据此推定适用于所有税种、所得或申报情形。', '',
                  '| 原件行号 | A列原值 | B列公式（原文） | B列缓存结果 |', '| --- | --- | --- | --- |'])
    for r in range(1,17):
        a, b = formulas['cells'].get(f'A{r}'), formulas['cells'].get(f'B{r}')
        if not a or not b or 'formula' not in b:
            raise ValueError('Formula worksheet changed; inspect before importing')
        used.update({('Sheet2',f'A{r}'),('Sheet2',f'B{r}')})
        lines.append(f'| {r} | {a["value"]} | `{b["formula"]}` | {b["cached"]} |')
    if empty['cells']:
        raise ValueError('Sheet3 is no longer empty')
    lines.extend(['', '## 工作表：Sheet3', '', '原工作表为空。', '', '## 需结合原件核对的写法', '',
                  '- 原表 J10 写作“不超过925元”，未在该单元格补写“/半天”；此处保留原文。',
                  '- 原表 J8 写作“1300元（人/次）”，没有“不超过”字样；此处保留原文。',
                  '- 纵向、横向、讲座费及公式示例分别保留，不相互套用；具体业务适用范围和后续文件仍需核对。'])
    all_cells = {(s['name'],a) for s in sheets for a in s['cells']}
    if used != all_cells:
        raise ValueError('Source cell coverage mismatch: ' + repr(sorted(all_cells-used)))
    return {'markdown': '\n'.join(lines)+'\n', 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'coverage': {'nonempty_cells':len(all_cells), 'rendered_cells':len(used),
                         'formula_cells':sum('formula' in c for s in sheets for c in s['cells'].values()),
                         'sheet_names':[s['name'] for s in sheets],
                         'merged_ranges':{s['name']:s['merges'] for s in sheets}}}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('file',type=Path)
    cli.add_argument('--json',action='store_true')
    args = cli.parse_args()
    result = convert(args.file)
    print(json.dumps(result,ensure_ascii=False,indent=2) if args.json else result['markdown'])
