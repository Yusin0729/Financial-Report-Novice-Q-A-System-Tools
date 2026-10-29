import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.mark_headings import mark_missing_headings
from functions.markdown_processing.note_processing import process_note_content


class FinancialHeadingTests(unittest.TestCase):
    def test_multi_year_description_requires_no_colon_or_length_limit(self):
        for title in ('112 及 111 年 度 所得稅主要組成如下',
                      '民國一一四年度及一一三年度，' + '說明'*30 + '。',
                      '112年度及111年度說明', '112及111及110年度比較',
                      '112 及 111 年度'):
            for prefix in ('', '## '):
                text = prefix + title + '\r\n'
                result = mark_missing_headings(text).markdown
                self.assertEqual(result, '## ' + title + '\r\n')
                self.assertEqual(mark_missing_headings(result).markdown, result)
        for text in ('本公司112及111年度之資訊', '112及111個項目', '112及年度'):
            self.assertEqual(mark_missing_headings(text).markdown, text)

    def test_numeric_lines_not_headings_and_existing_double_hash_removed(self):
        for value in ('4.375%', '$10,996', '(2,651)', '-2,651', '123', '4.375', '４．３７５％'):
            self.assertEqual(mark_missing_headings(value).markdown, value)
            self.assertEqual(mark_missing_headings('## ' + value).markdown, value)
        self.assertEqual(mark_missing_headings('4. 現金及約當現金').markdown, '## 4. 現金及約當現金')
        self.assertEqual(mark_missing_headings('112 年 12 月 31 日').markdown, '## 112 年 12 月 31 日')

    def test_note_and_table_protection_and_existing_colon_merge(self):
        prefix = '## 4.375%\n112及111年度前段說明\n<note>\n'
        suffix = ('## 4.375%\n112及111年度後段說明\n'
                  '<table>\n## 4.375%\n112及111年度表內說明\n</table>\n')
        result = process_note_content(prefix + suffix)[0].markdown
        self.assertEqual(result, prefix + suffix.replace('## 4.375%\n112及111年度後段說明',
                                                         '4.375%\n## 112及111年度後段說明', 1))
        self.assertEqual(mark_missing_headings('112及111年度，\n所得稅主要組成如下：').markdown,
                         '## 112及111年度， 所得稅主要組成如下：')


if __name__ == '__main__':
    unittest.main()
