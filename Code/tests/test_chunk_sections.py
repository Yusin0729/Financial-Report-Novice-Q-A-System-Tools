"""查核報告只按其區域內真實##識別，不處理表格或程式碼中的假標題。"""
import sys
import hashlib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.comment_tagging import tag_comments
from functions.chunking.parser import parse_tagged
from functions.chunking.sections import classify_section_events
from functions.chunking.chunks import chunk_tagged
from schemas import TaggingMetadata


class SectionEventTests(unittest.TestCase):
    def events(self, source):
        tagged = tag_comments(source, None, TaggingMetadata(report_year='2025', stock_code='2330')).markdown
        return classify_section_events(parse_tagged(tagged, expected_identity=('2025','2330')), tagged)

    def test_audit_each_heading_is_one_chunk_even_over_target_and_across_pages(self):
        raw = ('<會計師查核報告>\n<!-- Page: 2330_2025_P4 -->\n'
               '## 查核意見\n'+'甲'*1500+'\n<!-- Page: 2330_2025_P5 -->\n'
               +'乙'*1500+'。\n## 查核意見之基礎\n依準則辦理。\n'
               '<note>\n<合併財務報告附註>\n<!-- Page: 2330_2025_P14 -->\n'
               '## 一、其他章節\n附註內容。\n')
        tagged = tag_comments(raw, None, TaggingMetadata(report_year='2025',stock_code='2330')).markdown
        result = chunk_tagged(tagged, identity=('2025','2330'), source_sha256=hashlib.sha256(tagged.encode()).hexdigest())
        chunks = result.document['chunks']
        self.assertEqual(len(chunks), 3)
        self.assertEqual([c['title']['main_title'] for c in chunks],
                         ['會計師查核報告','會計師查核報告','合併財務報告附註'])
        self.assertEqual(chunks[0]['title']['heading']['text'], '查核意見')
        self.assertEqual(chunks[0]['page'], [4,5])
        self.assertIn('乙'*1500, chunks[0]['content'])
        self.assertEqual(result.excluded_prefix_end, 0)

    def test_no_company_history_or_hd2_does_not_discard_text(self):
        raw = '<會計師查核報告>\n<!-- Page: 2330_2025_P4 -->\n## 查核意見\n正文。\n'
        tagged = tag_comments(raw, None, TaggingMetadata(report_year='2025',stock_code='2330')).markdown
        result = chunk_tagged(tagged, identity=('2025','2330'), source_sha256=hashlib.sha256(tagged.encode()).hexdigest())
        self.assertEqual(len(result.document['chunks']), 1)
        self.assertIn('正文。', result.document['chunks'][0]['content'])

    def test_audit_titles_and_note_boundary(self):
        source = ('<會計師查核報告>\n<!-- Page: 2330_2025_P4 -->\n'
                  '## Deloitte\n## 查核意見\n正文\n<note>\n<合併財務報告附註>\n'
                  '<!-- Page: 2330_2025_P14 -->\n## 一、公司沿革\n公司正文\n')
        events = self.events(source)
        self.assertEqual([e.title for e in events if e.kind == 'audit_heading'], ['Deloitte','查核意見'])
        self.assertEqual([e.title for e in events if e.kind == 'section'],
                         ['會計師查核報告','合併財務報告附註','合併財務報告附註'])

    def test_code_comments_and_tables_do_not_create_sections(self):
        source = ('<!-- Page: 2330_2025_P4 -->\n<note>\n'
                  '```\n<會計師查核報告>\n## 假標題\n```\n'
                  '<table><tr><td>\n<會計師查核報告>\n</td></tr></table>\n'
                  '<!--\n<會計師查核報告>\n-->\n## 一、附註\n')
        events = self.events(source)
        self.assertFalse(any(e.kind == 'audit_heading' for e in events))
        self.assertEqual([e.title for e in events if e.kind == 'section'], ['合併財務報告附註'])


if __name__ == '__main__':
    unittest.main()
