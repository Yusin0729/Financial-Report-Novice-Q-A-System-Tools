"""候選內清理、原始位置紀錄、重跑及第三／四階段相容；不寫檔。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.suspected_table_spaces import clean_suspected_table_spaces
from functions.markdown_processing.note_processing import process_note_content
from functions.markdown_processing.mark_headings import TableBoundaryError
from functions.markdown_processing.comment_tagging import tag_comments
from functions.chunking.chunks import chunk_tagged
from config.chunking import ChunkSettings
from schemas import TaggingMetadata


class SuspectedSpacesTests(unittest.TestCase):
    def test_only_candidate_whitespace_removed_without_joining_nonempty_lines(self):
        before = '英文 words\n\n<table><tr><td> 100 </td><td></td></tr></table>\n'
        inner = '項 目\r\n\r\n $ 1,200 \r\n\t( 2,651 )\r\n\u3000\t\r\n - 1.25 % \r\n'
        block = '<cannotfindtable>\r\n'+inner+'</cannotfindtable>\r\n'
        after = '\n正文 text 100\n\n'
        value, report = clean_suspected_table_spaces(before+block+after)
        expected = '<cannotfindtable>\r\n項目\r\n$1,200\r\n(2,651)\r\n-1.25%\r\n</cannotfindtable>\r\n'
        self.assertEqual(value, before+expected+after)
        self.assertEqual(report['removed_blank_lines'], 2)
        self.assertEqual(report['changed_block_count'], 1)
        self.assertEqual(clean_suspected_table_spaces(value)[0], value)

    def test_fake_markers_protected_and_html_attributes_not_damaged(self):
        literal = '```text\n<cannotfindtable>\n a b \n</cannotfindtable>\n```\n'
        literal += '<!--\n<cannotfindtable>\n a b \n</cannotfindtable>\n-->\n'
        literal += '<table><tr><td> a b </td></tr></table>\n'
        self.assertEqual(clean_suspected_table_spaces(literal)[0], literal)
        block = '<cannotfindtable>\n'+literal+' $ 20 \n</cannotfindtable>\n'
        self.assertEqual(clean_suspected_table_spaces(block)[0],
                         '<cannotfindtable>\n'+literal+'$20\n</cannotfindtable>\n')
        span = '<cannotfindtable>\n<span class="a b">內 文</span>\n</cannotfindtable>\n'
        self.assertEqual(clean_suspected_table_spaces(span)[0], span.replace('內 文', '內文'))

    def test_malformed_boundaries_fail(self):
        for value in ('<cannotfindtable>\n a b\n', '</cannotfindtable>\n',
                      '<cannotfindtable>\n<cannotfindtable>\n</cannotfindtable>\n'):
            with self.assertRaises(TableBoundaryError):
                clean_suspected_table_spaces(value)

    def test_detection_pipeline_and_original_heading_lines_remain_traceable(self):
        raw = '<note>\n<!-- Page: 2330_2025_P15 -->\n## 一、政策\n項 目\n\n $ \n 1,200 \n( 20 )\n - 30 \n\n## (一)說明\n內文。\n'
        result, _, scope = process_note_content(raw)
        self.assertIn('<cannotfindtable>\n項目\n$\n1,200\n(20)\n-30\n</cannotfindtable>', result.markdown)
        self.assertEqual(scope['suspected_table_detection']['candidates'][0]['start_line'], 4)
        self.assertEqual(scope['suspected_table_whitespace_cleanup']['block_count'], 1)
        self.assertEqual(process_note_content(result.markdown)[0].markdown, result.markdown)
        tagged = tag_comments(result.markdown, None, TaggingMetadata(report_year='2025',stock_code='2330')).markdown
        doc = chunk_tagged(tagged, identity=('2025','2330'), source_sha256='a'*64,
                           config=ChunkSettings(mode='parent_child')).document
        tables = [c for c in doc['chunks'] if c['content_type'] == 'table']
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]['table_completeness'], 0)
        self.assertIn('$\n1,200\n(20)\n-30', tables[0]['content'])


if __name__ == '__main__':
    unittest.main()
