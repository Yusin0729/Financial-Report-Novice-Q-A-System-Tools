import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.markdown_headings import EXCLUDED_ENDINGS
from functions.markdown_processing.mark_headings import mark_missing_headings


class EnglishHeadingTests(unittest.TestCase):
    def test_long_english_markers_and_idempotence(self):
        for prefix in ('A.', 'a.', '(A)', '(a)', '（B）', '- b.'):
            text = prefix + ' ' + '標題內容'*20
            result = mark_missing_headings(text).markdown
            self.assertEqual(result, '## ' + text)
            self.assertEqual(mark_missing_headings(result).markdown, result)

    def test_punctuation_and_empty_rejected_in_plain_and_existing_headings(self):
        for tail in ('', '   ', *(f'說明{p}' for p in EXCLUDED_ENDINGS)):
            text = 'A. ' + tail
            self.assertEqual(mark_missing_headings(text).markdown, text)
            self.assertEqual(mark_missing_headings('## ' + text).markdown, text)

    def test_numeric_limit_and_protected_tables_unchanged(self):
        for text in ('1. ' + '長'*21, '(1) 說明。', '1、暫未擴充',
                     '<table>\nA. 表內\n</table>\n',
                     '| A. 欄位 |\n| --- |\n| (a) 資料 |\n'):
            self.assertEqual(mark_missing_headings(text).markdown, text)


if __name__ == '__main__':
    unittest.main()
