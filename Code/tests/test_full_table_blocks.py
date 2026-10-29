"""疑似表格使用專用開始邊界，其原文與接表條件仍保留。"""
import hashlib
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.block_boundaries import add_block_boundaries
from functions.markdown_processing.comment_tagging import tag_comments
from functions.markdown_processing.mark_headings import TableBoundaryError
from functions.chunking.chunks import chunk_tagged_legacy as chunk_tagged
from schemas import TaggingMetadata

PAGE = '<!-- Page: 2330_2025_P15 -->\n'
FULL = '<cannotfindtable>\n稅額\n$\n123\n,\n456 )\n</cannotfindtable>\n'
TABLE = '<table><tr><td>456</td></tr></table>'


class FullTableBlockTests(unittest.TestCase):
    def test_full_table_closes_content_and_keeps_exact_candidate(self):
        text = PAGE+'前文\n'+FULL+'後文\n'
        out, counts, _ = add_block_boundaries(text)
        self.assertIn('</content_end>\n<fulltablestart>\n'+FULL+'<table_end>\n', out)
        self.assertNotIn('<table_start>', out)
        self.assertEqual(counts, {'page': 1, 'table': 1, 'content': 2, 'full_table': 1})
        body = re.search(r'<fulltablestart>\n(.*?)<table_end>', out, re.S)[1]
        self.assertEqual(body, FULL)
        self.assertNotIn('<content_start>', body)

    def test_normal_and_full_table_are_separate_without_continuation(self):
        out, counts, _ = add_block_boundaries(PAGE+TABLE+'\n'+FULL)
        self.assertEqual(out.count('<table_start>'), 1)
        self.assertEqual(out.count('<fulltablestart>'), 1)
        self.assertEqual(counts['table'], 2)

    def test_continued_candidates_keep_one_special_table_across_pages(self):
        for marker in ('接 次 頁', '承\u3000前\u3000頁'):
            text = PAGE+FULL+marker+'\n<!-- Page: 2330_2025_P16 -->\n'+FULL
            out, counts, _ = add_block_boundaries(text)
            self.assertEqual(out.count('<fulltablestart>'), 1)
            self.assertEqual(out.count('<table_end>'), 1)
            self.assertEqual(out.count(FULL), 2)
            self.assertEqual(counts['page'], 2)
            self.assertIn('<page_end>\n<!-- Page: 2330_2025_P16 -->\n<page_start>', out)

    def test_mixed_continued_group_remains_flagged_as_uncertain(self):
        for text in (PAGE+TABLE+'\n接次頁\n'+FULL,
                     PAGE+FULL+'承前頁\n'+TABLE):
            out, counts, _ = add_block_boundaries(text)
            self.assertEqual(out.count('<fulltablestart>'), 1)
            self.assertNotIn('<table_start>', out)
            self.assertEqual(counts['table'], 1)
            self.assertIn(FULL, out)
            self.assertIn(TABLE, out)

    def test_fake_candidate_in_protected_content_not_wrapped(self):
        for literal in ('```\n'+FULL+'```\n', '<!--\n'+FULL+'-->\n',
                        '<table><tr><td>\n'+FULL+'</td></tr></table>\n'):
            out, _, _ = add_block_boundaries(PAGE+literal)
            self.assertNotIn('<fulltablestart>', out)
            self.assertIn(literal, out)

    def test_nested_html_in_real_candidate_not_double_wrapped(self):
        full = '<cannotfindtable>\n文字\n'+TABLE+'\n</cannotfindtable>\n'
        out, counts, _ = add_block_boundaries(PAGE+full)
        self.assertIn('<fulltablestart>\n'+full+'<table_end>', out)
        self.assertEqual(counts['table'], 1)
        self.assertNotIn('<table_start>', out)

    def test_malformed_and_already_wrapped_inputs_rejected(self):
        for candidate in ('<cannotfindtable>\n資料', '</cannotfindtable>\n',
                          '<cannotfindtable>\n<cannotfindtable>\n</cannotfindtable>\n'):
            with self.assertRaises(TableBoundaryError):
                add_block_boundaries(PAGE+candidate)
        once, _, _ = add_block_boundaries(PAGE+FULL)
        with self.assertRaisesRegex(ValueError, '重複'):
            add_block_boundaries(once)

    def test_tagging_and_existing_chunk_reader_keep_candidate_content(self):
        source = PAGE+'## 一、公司沿革\n'+FULL
        tagged = tag_comments(source, None, TaggingMetadata(report_year='2025', stock_code='2330'))
        self.assertIn('<fulltablestart>\n'+FULL+'<table_end>', tagged.markdown)
        result = chunk_tagged(tagged.markdown, identity=('2025', '2330'),
                              source_sha256=hashlib.sha256(tagged.markdown.encode()).hexdigest())
        tables = [c for c in result.document['chunks'] if c['content_type'] == 'table']
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]['content'], FULL)
        self.assertTrue(result.document['parents'])
        self.assertIn('<fulltablestart>', result.markdown)

    def test_crlf_candidate_is_not_downgraded_to_body_text(self):
        full = FULL.replace('\n', '\r\n')
        out = tag_comments(PAGE+'## 一、公司沿革\n'+full, None,
                           TaggingMetadata(report_year='2025', stock_code='2330')).markdown
        result = chunk_tagged(out, identity=('2025', '2330'),
                              source_sha256=hashlib.sha256(out.encode()).hexdigest())
        child = next(c for c in result.document['chunks'] if c['content_type'] == 'table')
        self.assertEqual(child['content'], full)
        self.assertIn('<fulltablestart>', result.markdown)


if __name__ == '__main__':
    unittest.main()
