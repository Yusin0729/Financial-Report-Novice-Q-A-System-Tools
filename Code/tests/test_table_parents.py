"""新表格年度、前置脈絡與附表父子切塊；僅本機合成資料。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_chunks import convert, tagged, page
from functions.markdown_processing.mark_headings import mark_missing_headings


def table(header='114年度', value='123'):
    return f'<table><tr><th>{header}</th></tr><tr><td>{value}</td></tr></table>\n'


class ParentTests(unittest.TestCase):
    def test_new_and_legacy_appendix_markers_keep_separate_parents(self):
        for prefix in ('# ', '#### '):
            raw = (page(15)+'## 一、公司沿革\n前文\n'+prefix+'附 表 一：資金貸與\n'+table()
                   +'接次頁\n'+prefix+'附 表 二：背書保證\n'+table())
            result = convert(tagged(raw)).document
            parents = [p for p in result['parents'] if p['appendix_id']]
            self.assertEqual([p['appendix_id'] for p in parents], ['附表一', '附表二'])
            self.assertTrue(all(p['content'].count('<table>') == 1 for p in parents))

    def test_table_years_and_context_do_not_use_body_dates(self):
        raw = page(15) + '## 一、公司沿革\n## (一) 現金\n' + table('114及113年度', '民國90年取得')
        result = convert(tagged(raw)).document
        child = result['chunks'][0]
        self.assertEqual(child['years'], [2024, 2025])
        self.assertEqual(child['table_context'], '(一) 現金')
        self.assertEqual(child['parent_id'], result['parents'][0]['chunk_id'])

    def test_prose_stops_year_search_but_not_heading_context(self):
        result = convert(tagged(page(15) + '## 一、公司沿革\n說明正文\n' + table('金額'))).document
        child = next(c for c in result['chunks'] if c['content_type'] == 'table')
        self.assertEqual(child['table_context'], '一、公司沿革')
        self.assertEqual(child['years'], [2025])
        self.assertEqual(child['year_sources'][0]['source'], 'document_year_fallback')

    def test_continued_table_has_page_children_and_exact_full_parent(self):
        raw = page(15) + '## 一、公司沿革\n' + table() + '接 次 頁\n' + page(16) + table('113年度')
        source = tagged(raw)
        result = convert(source).document
        self.assertEqual(len(result['parents']), 1)
        self.assertEqual([c['page'] for c in result['chunks']], [[15], [16]])
        self.assertEqual([c['years'] for c in result['chunks']], [[2024, 2025], [2024, 2025]])
        self.assertEqual(''.join(c['content'] for c in result['chunks']), result['parents'][0]['content'])
        for child in result['chunks']:
            self.assertEqual(''.join(source[s['start']:s['end']] for s in child['source_spans']), child['content'])

    def test_appendix_groups_all_tables_and_text_until_next_number(self):
        raw = (page(15) + '## 一、公司沿革\n前文\n附表一：資金貸與\n單位：千元\n' + table() +
               page(16) + '附表一第2頁\n跨頁說明\n' + table('113年度') +
               '承前頁\n附表二：背書保證\n單位：千元\n' + table('金額'))
        result = convert(tagged(mark_missing_headings(raw).markdown)).document
        parents = [p for p in result['parents'] if p['appendix_id']]
        self.assertEqual([p['appendix_id'] for p in parents], ['附表一', '附表二'])
        self.assertEqual(parents[0]['content'].count('<table>'), 2)
        self.assertIn('單位：千元', parents[0]['content'])
        self.assertIn('跨頁說明', parents[0]['content'])
        self.assertNotIn('附表二', parents[0]['content'])
        first = [c for c in result['chunks'] if c['appendix_id'] == '附表一']
        self.assertEqual([c['page'] for c in first], [[15], [16]])
        self.assertEqual(len({c['parent_id'] for c in first}), 1)

    def test_skip_previous_table_but_not_prose_for_context(self):
        raw = page(15) + '## 一、公司沿革\n## (一) 現金\n' + table() + table('金額')
        result = convert(tagged(raw)).document
        self.assertEqual([p['table_context'] for p in result['parents']], ['(一) 現金', '(一) 現金'])


if __name__ == '__main__':
    unittest.main()
