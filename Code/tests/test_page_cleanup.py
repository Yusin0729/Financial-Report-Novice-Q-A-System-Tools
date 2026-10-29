"""processed 清頁碼：保留來源標記、表格、程式碼、正文數值與行尾。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.page_cleanup import remove_standalone_page_numbers
from functions.markdown_processing.mark_headings import TableBoundaryError


class PageCleanupTests(unittest.TestCase):
    def test_spaced_digits_and_page_metadata_unchanged(self):
        marker = '<!-- Page: 2330_2025_P51 -->'
        text = marker+'\n5 1\n正文\n5\t1\n\n- 5 2 -\n'
        # 末行是帶橫線頁碼；先前正文中的5 1不能被當成純數字頁尾。
        cleaned, removed = remove_standalone_page_numbers(text)
        self.assertEqual(cleaned, marker+'\n5 1\n正文\n5\t1\n\n')
        self.assertEqual([r['text'] for r in removed], ['- 5 2 -'])
        for digits in ('5 1', '5\t1', '5\u30001'):
            source = marker+'\n正文\n'+digits+'\n'
            cleaned, removed = remove_standalone_page_numbers(source)
            self.assertEqual(cleaned, marker+'\n正文\n')
            self.assertEqual(removed[0]['text'], digits)
        for tail in ('5 2', '5.1', '    5 1', '<table>\n5 1\n</table>'):
            text = marker+'\n'+tail
            self.assertEqual(remove_standalone_page_numbers(text)[0], text)

    def test_bare_footer_matches_page_and_only_last_nonblank_line(self):
        text = ('<!-- Page: 2330_2025_P15 -->\r\n15\r\n正文\r\n15\r\n\r\n'
                '<!-- PDF_PAGE: 16 -->\n正文\n17\n'
                '<!-- PDF_PAGE: 18 -->\n正文\n18')
        cleaned, removed = remove_standalone_page_numbers(text)
        self.assertEqual([x['text'] for x in removed], ['15', '18'])
        self.assertIn('P15 -->\r\n15\r\n正文\r\n\r\n', cleaned)
        self.assertIn('正文\n17\n', cleaned)
        self.assertEqual(remove_standalone_page_numbers(cleaned), (cleaned, ()))

    def test_no_page_marker_or_protected_numbers_are_preserved(self):
        for text in ('正文\n15', '<!-- PDF_PAGE: 15 -->\n    15',
                     '<!-- PDF_PAGE: 15 -->\n<table>\n15\n</table>',
                     '<!-- PDF_PAGE: 15 -->\n```\n15\n```',
                     '<!--\n<!-- PDF_PAGE: 15 -->\n-->\n15',
                     '<table>\n<!-- PDF_PAGE: 15 -->\n</table>\n15'):
            self.assertEqual(remove_standalone_page_numbers(text), (text, ()))

    def test_only_standalone_footer_lines_outside_protected_content_removed(self):
        keep = ('<!-- Page: 2330_2025_P2 -->\r\n<!-- PDF_PAGE: 3 -->\n'
                '金額 -1；區間 1-3；- 4 - 正文\n'
                '<table>\n<tr><td>- 5 -</td></tr>\n- 6 -\n</table>\n'
                '```text\n- 7 -\n```\n    - 8 -\n<!--\n- 9 -\n-->\n')
        text = '- 1 -\r\n' + keep + ' -10- '
        cleaned, removed = remove_standalone_page_numbers(text)
        self.assertEqual(cleaned, keep)
        self.assertEqual([item['text'] for item in removed], ['- 1 -', ' -10- '])
        self.assertEqual(removed[0]['source_line'], 1)
        self.assertEqual(remove_standalone_page_numbers(cleaned), (cleaned, ()))

    def test_malformed_table_rejected_without_partial_cleanup(self):
        with self.assertRaises(TableBoundaryError):
            remove_standalone_page_numbers('- 1 -\n<table>\n- 2 -\n')


if __name__ == '__main__':
    unittest.main()
