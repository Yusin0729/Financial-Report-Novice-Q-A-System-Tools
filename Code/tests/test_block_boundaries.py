"""驗證區塊正確巢狀、表格精確原文及頁尾收尾；全部本機。"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.block_boundaries import add_block_boundaries
from functions.markdown_processing.mark_headings import _protected_lines, TableBoundaryError
from functions.markdown_processing.comment_tagging import tag_comments
from schemas import TaggingMetadata
from test_comment_tagging import TEXT, TABLE, toc_fixture


class BlockBoundaryTests(unittest.TestCase):
    def test_unchanged_main_and_page_metadata_do_not_split_content(self):
        text = ('<!-- PDF_PAGE: 1 -->\n<!-- MAIN_TITLE: 同一大標 -->\n前頁正文\n'
                '<!-- PDF_PAGE: 2 -->\n<!-- MAIN_TITLE: 同一大標 -->\n'
                '<!-- CROSS_PAGE_ITEMS: #/texts/1 -->\n後頁正文\n'
                '<!-- PDF_PAGE: 3 -->\n<!-- MAIN_TITLE: 新大標 -->\n新大標正文\n')
        tagged, counts, _ = add_block_boundaries(text)
        contents = re.findall(r'<content_start>\n(.*?)</content_end>', tagged, re.S)
        self.assertEqual(counts['content'], 2)
        self.assertIn('前頁正文', contents[0])
        self.assertIn('後頁正文', contents[0])
        self.assertNotIn('新大標正文', contents[0])
        self.assert_nested(tagged)

    def test_content_continues_across_pages_until_heading_or_table(self):
        text = ('<!-- Page: 2330_2025_P18 -->\n第一頁正文\n'
                '<!-- Page: 2330_2025_P19 -->\n第二頁正文\n'
                '<hd3>(二) 新標題</hd3>\n新章節正文\n'
                '<table><tr><td>表格</td></tr></table>\n表後正文\n')
        tagged, counts, _ = add_block_boundaries(text)
        first = re.findall(r'<content_start>\n(.*?)</content_end>', tagged, re.S)[0]
        self.assertIn('第一頁正文', first)
        self.assertIn('第二頁正文', first)
        self.assertIn('<page_end>\n<!-- Page: 2330_2025_P19 -->\n<page_start>', first)
        self.assertNotIn('<hd3>', first)
        self.assertEqual(counts, {'page': 2, 'table': 1, 'content': 3})
        self.assert_nested(tagged)

    def test_either_continuation_marker_joins_complete_tables_across_pages(self):
        one = '<table><tr><td>第一頁列</td></tr></table>'
        two = '<table><tr><td>第二頁列</td></tr></table>'
        for marker in ('（接 次 頁）', '## （承\u3000前\u3000頁）', '接次頁\n承前頁'):
            with self.subTest(marker=marker):
                text = ('<!-- Page: 2330_2025_P18 -->\n' + one + '\n' + marker + '\n'
                        '<!-- Page: 2330_2025_P19 -->\n接續表頭\n' + two + '\n表後正文\n')
                joins = []
                tagged, counts, _ = add_block_boundaries(text, continuation_joins=joins)
                self.assertEqual(counts, {'page': 2, 'table': 1, 'content': 1})
                table = re.search(r'<table_start>\n(.*?)<table_end>', tagged, re.S)[1]
                for original in (one, two, marker, '接續表頭'):
                    self.assertIn(original, table)
                self.assertIn('<page_end>\n<!-- Page: 2330_2025_P19 -->\n<page_start>\n', table)
                self.assertEqual(re.findall(r'<table>.*?</table>', tagged, re.S), [one, two])
                self.assertEqual((joins[0]['left_table'], joins[0]['right_table']), (1, 2))
                self.assert_nested(tagged)

    def test_continuation_groups_chain_but_plain_page_break_does_not_join(self):
        tables = [f'<table><tr><td>{n}</td></tr></table>' for n in range(4)]
        text = ('<!-- PDF_PAGE: 1 -->\n' + tables[0] + '\n接次頁\n<!-- PDF_PAGE: 2 -->\n' +
                tables[1] + '\n承前頁\n<!-- PDF_PAGE: 3 -->\n' + tables[2] +
                '\n<!-- PDF_PAGE: 4 -->\n' + tables[3] + '\n')
        joins = []
        tagged, counts, _ = add_block_boundaries(text, continuation_joins=joins)
        self.assertEqual(counts['table'], 2)
        self.assertEqual(len(joins), 2)
        groups = re.findall(r'<table_start>\n(.*?)<table_end>', tagged, re.S)
        self.assertTrue(all(t in groups[0] for t in tables[:3]))
        self.assertNotIn(tables[3], groups[0])
        self.assert_nested(tagged)

    def test_continuation_marker_inside_table_comment_or_code_does_not_join(self):
        one = '<table><tr><td>接次頁</td></tr></table>'
        two = '<table><tr><td>承前頁</td></tr></table>'
        for gap in ('\n<!-- Page: 2330_2025_P2 -->\n',
                    '\n<!-- 接次頁 -->\n', '\n```\n承 前 頁\n```\n'):
            with self.subTest(gap=gap):
                tagged, counts, _ = add_block_boundaries('<!-- PDF_PAGE: 1 -->\n' + one + gap + two)
                self.assertEqual(counts['table'], 2)
                self.assertIn(one, tagged)
                self.assertIn(two, tagged)
                self.assert_nested(tagged)

    def test_page_preface_is_outside_previous_and_current_page(self):
        title = '<!-- MAIN_TITLE: 合併財務報表附錄 -->'
        text = '<!-- PDF_PAGE: 1 -->\n前段\n<!-- PDF_PAGE: 2 -->\n附錄\n<!-- PDF_PAGE: 3 -->\n後段\n'
        tagged, counts, _ = add_block_boundaries(text, page_prefaces={2: title})
        self.assertIn('<page_end>\n' + title + '\n<!-- PDF_PAGE: 2 -->\n<page_start>\n', tagged)
        self.assertEqual(tagged.count(title), 1)
        self.assertEqual(counts['page'], 3)
        self.assert_nested(tagged)

    def assert_nested(self, text):
        lines = text.splitlines(keepends=True)
        protected = _protected_lines(text, lines)
        # 頁面與內容各自成對，可交錯跨頁，不要求page包住整個content/table。
        page_open, block = False, None
        starts = {'<table_start>': 'table', '<content_start>': 'content'}
        ends = {'<table_end>': 'table', '</content_end>': 'content'}
        for index, line in enumerate(lines):
            if index in protected:
                continue
            token = line.strip()
            if token == '<page_start>':
                self.assertFalse(page_open)
                page_open = True
            elif token == '<page_end>':
                self.assertTrue(page_open)
                page_open = False
            elif token in starts:
                self.assertIsNone(block)
                block = starts[token]
            elif token in ends:
                self.assertEqual(block, ends[token])
                block = None
        self.assertFalse(page_open)
        self.assertIsNone(block)

    def test_integration_content_metadata_headings_tables_and_pages(self):
        result = tag_comments(TEXT, toc_fixture(), TaggingMetadata(report_year='2025', stock_code='2330'))
        tagged = result.markdown
        self.assertEqual(result.block_counts['page'], 3)
        self.assertEqual(result.block_counts['table'], 1)
        self.assertIn('<table_start>\n' + TABLE.rstrip('\n') + '\n<table_end>', tagged)
        self.assertIn('<!-- PDF_PAGE: 1 -->\n<page_start>', tagged)
        self.assertTrue(tagged.endswith('<page_end>\n'))
        self.assert_nested(tagged)
        contents = re.findall(r'<content_start>\n(.*?)</content_end>', tagged, re.S)
        self.assertTrue(contents)
        for content in contents:
            self.assertNotRegex(content, r'<hd\d+>')
            self.assertNotIn('<!-- SUB_TITLE:', content)
            self.assertNotIn('<!-- HEADING_', content)
            self.assertNotIn('<table>', content)
            self.assertNotIn('## 一', content)

    def test_hd_lines_split_content_and_remain_outside_content_blocks(self):
        text = ('<!-- PDF_PAGE: 1 -->\n前段\n<hd2>一、政策</hd2>\n'
                '<hd3></hd3>\n後段\n<hd10>細節</hd10>\n末段\n')
        tagged, counts, _ = add_block_boundaries(text)
        self.assertEqual(counts['content'], 3)
        self.assertIn('</content_end>\n<hd2>一、政策</hd2>\n<hd3></hd3>\n<content_start>', tagged)
        for content in re.findall(r'<content_start>\n(.*?)</content_end>', tagged, re.S):
            self.assertNotRegex(content, r'<hd\d+>')
        self.assert_nested(tagged)

    def test_blank_lines_and_page_changes_keep_same_content(self):
        text = '<!-- Page: 2330_2025_P1 -->\n第一段\n\n第二段\n<!-- Page: 2330_2025_P2 -->\n\n'
        tagged, counts, _ = add_block_boundaries(text)
        self.assertEqual(counts, {'page': 2, 'table': 0, 'content': 1})
        self.assertIn('<content_start>\n第一段\n\n第二段\n<page_end>', tagged)
        self.assertIn('<!-- Page: 2330_2025_P1 -->\n<page_start>\n', tagged)
        self.assertIn('<page_end>\n<!-- Page: 2330_2025_P2 -->\n<page_start>\n', tagged)
        self.assert_nested(tagged)

    def test_whitespace_only_lines_preserve_content_and_original_spaces(self):
        text = '<!-- Page: 2330_2025_P1 -->\r\n第一段\r\n \t\u3000\r\n\r\n第二段\r\n'
        tagged, counts, _ = add_block_boundaries(text)
        self.assertEqual(counts['content'], 1)
        self.assertIn('第一段\r\n \t\u3000\r\n\r\n第二段\r\n', tagged)
        self.assert_nested(tagged)

    def test_blank_lines_inside_tables_candidates_and_code_do_not_close_blocks(self):
        literals = [
            '<table><tr><td>前段\n\n後段</td></tr></table>',
            '<cannotfindtable>\n前段\n\n後段\n</cannotfindtable>',
            '```text\n前段\n\n後段\n```',
        ]
        for literal in literals:
            with self.subTest(literal=literal):
                tagged, _, _ = add_block_boundaries('<!-- Page: 2330_2025_P1 -->\n'+literal+'\n')
                self.assertIn(literal, tagged)
                self.assertEqual(tagged.count('</content_end>'), 1 if literal.startswith('```') else 0)

    def test_last_page_marker_without_newline_gets_separate_page_start(self):
        tagged, counts, added = add_block_boundaries('<!-- Page: 2330_2025_P25 -->')
        self.assertEqual(tagged, '<!-- Page: 2330_2025_P25 -->\n<page_start>\n<page_end>\n')
        self.assertEqual(counts, {'page': 1, 'table': 0, 'content': 0})
        self.assertEqual(added, 1)

    def test_two_inline_tables_preserve_exact_table_substrings(self):
        one = '<table><tr><td>1</td></tr></table>'
        two = '<table><tr><td>2</td></tr></table>'
        text = '<!-- PDF_PAGE: 1 -->\n前文' + one + '中間' + two + '後文'
        tagged, counts, added = add_block_boundaries(text)
        self.assertEqual(re.findall(r'<table>.*?</table>', tagged, re.S), [one, two])
        self.assertEqual(counts, {'page': 1, 'table': 2, 'content': 3})
        self.assertGreater(added, 0)
        for word in ('前文', '中間', '後文'):
            self.assertIn('<content_start>\n' + word + '\n</content_end>', tagged)
        self.assert_nested(tagged)

    def test_code_and_comments_containing_fake_tags_are_preserved(self):
        code = '```html\n<table>\n## 假標題\n<page_start>\n```\n'
        comment = '<!--\n<page_start>\n-->\n'
        tagged, counts, _ = add_block_boundaries('<!-- PDF_PAGE: 1 -->\n' + code + comment)
        self.assertEqual(counts, {'page': 1, 'table': 0, 'content': 1})
        self.assertIn(code, tagged)
        self.assertIn(comment, tagged)
        self.assert_nested(tagged)

    def test_last_line_without_eol_and_table_page_marker_not_real_boundary(self):
        text = '<!-- PDF_PAGE: 1 -->\r\n<table>\n<!-- PDF_PAGE: 2 -->\n</table>\r\n最後一行'
        tagged, counts, added = add_block_boundaries(text)
        self.assertEqual(counts, {'page': 1, 'table': 1, 'content': 1})
        self.assertIn('<!-- PDF_PAGE: 1 -->\r\n', tagged)
        self.assertIn('<table>\n<!-- PDF_PAGE: 2 -->\n</table>', tagged)
        self.assertGreater(added, 0)
        self.assert_nested(tagged)

    def test_repeated_tags_and_broken_table_are_rejected(self):
        tagged, _, _ = add_block_boundaries('<!-- PDF_PAGE: 1 -->\n文字\n')
        with self.assertRaisesRegex(ValueError, '重複'):
            add_block_boundaries(tagged)
        with self.assertRaises(TableBoundaryError):
            add_block_boundaries('<!-- PDF_PAGE: 1 -->\n<table>\n')


if __name__ == '__main__':
    unittest.main()
