import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tax_table', ROOT / 'tools/parse_consultation_tax_table.py')
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
SOURCE = ROOT / 'school-assets/forms/21fd483497f88408-专家咨询费税前对照表.xlsx'


class ConsultationTableTests(unittest.TestCase):
    def test_original_content_and_formula_caches_are_preserved(self):
        result = parser.convert(SOURCE)
        self.assertEqual(result['coverage']['nonempty_cells'], 121)
        self.assertEqual(result['coverage']['rendered_cells'], 121)
        self.assertEqual(result['coverage']['formula_cells'], 16)
        sheets = parser.read_workbook(SOURCE)
        self.assertEqual(len(sheets[0]['merges']), 31)
        self.assertFalse(sheets[2]['cells'])
        for row in range(1,17):
            cell = sheets[1]['cells'][f'B{row}']
            self.assertEqual(cell['formula'], f'=A{row}-(A{row}-800)*0.2')
            self.assertIn(f'`{cell["formula"]}` | {cell["cached"]} |', result['markdown'])
        self.assertEqual(sheets[1]['cells']['B9']['cached'], '2400')

    def test_scopes_merges_and_original_qualifiers_remain_distinct(self):
        text = parser.convert(SOURCE)['markdown']
        for phrase in ('纵向科研项目专家咨询费标准', '税后标准（元/人/天）',
                       '税前标准（元/人/天）', '横向科研项目专家咨询费标准（税前）',
                       '讲座费按照实际发生的学时计算，每半天最多按4学时计算。',
                       '不超过925元', '1300元（人/次）', '原工作表为空。'):
            self.assertIn(phrase, text)
        self.assertEqual(text.count('<table>'), 3)
        self.assertIn('colspan="3"', text)
        self.assertIn('rowspan="3"', text)
        self.assertIn('不作补写', text)
        self.assertIn('共享公式按 Excel 的相对引用展开', text)

    def test_knowledge_snapshot_matches_the_checked_parser_output(self):
        records = [json.loads(line) for line in (ROOT / 'skills/shu-baoxiao/references/knowledge/documents.jsonl').read_text().splitlines()]
        doc = next(d for d in records if d['id']=='21fd483497f88408')
        result = parser.convert(SOURCE)
        self.assertEqual(doc['text'], result['markdown'])
        self.assertEqual(doc['github_backup']['sha256'], result['source_sha256'])
        self.assertEqual(doc['provenance']['structure_coverage'], result['coverage'])
        self.assertEqual(doc['effectivity'], 'unverified')


if __name__ == '__main__':
    unittest.main()
