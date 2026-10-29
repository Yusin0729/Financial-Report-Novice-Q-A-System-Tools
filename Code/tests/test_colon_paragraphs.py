"""冒號段落不能破壞表格、頁序與既有特殊標題。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.mark_headings import mark_missing_headings


class ColonParagraphTests(unittest.TestCase):
    def test_full_stop_splits_inline_and_multiline_without_losing_text(self):
        cases = {
            '前面是一般說明。所得稅主要組成如下：':
                '前面是一般說明。\n## 所得稅主要組成如下：',
            '第一句。第二句。\r\n所得稅\r\n組成如下：\r\n':
                '第一句。第二句。\r\n## 所得稅 組成如下：\r\n',
            '較早說明：\n正文。下一段\n如下：\n':
                '## 較早說明：\n正文。\n## 下一段 如下：\n',
            '1. 前項正文。2. 本項說明如下：\n':
                '1. 前項正文。\n## 2. 本項說明如下：\n',
            'A. 金額1.5\n說明如下：\n':
                '## A. 金額1.5 說明如下：\n',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                result = mark_missing_headings(source).markdown
                self.assertEqual(result, expected)
                self.assertEqual(mark_missing_headings(result).markdown, result)

    def test_numbered_items_cannot_merge_into_next_colon_heading(self):
        text = '1. ' + '完整正文'*20 + '。\n2. 本公司尚未採用：\n'
        result = mark_missing_headings(text).markdown
        self.assertEqual(result, text.replace('2. 本公司尚未採用：', '## 2. 本公司尚未採用：'))
        self.assertEqual(mark_missing_headings(result).markdown, result)

    def test_wrapped_numbered_colon_collects_only_its_own_item(self):
        for marker in ('(1)', '(一)', 'A.', 'a.', '（A）', '- (2)', '## 二 、'):
            text = '上一段正文。\n' + marker + ' 本項\n說明如下：\n'
            result = mark_missing_headings(text).markdown
            title = marker.removeprefix('## ') + ' 本項 說明如下：'
            self.assertEqual(result, '上一段正文。\n## ' + title + '\n')
            self.assertEqual(mark_missing_headings(result).markdown, result)

    def test_merge_only_up_to_last_colon_with_original_line_reference(self):
        text = '\n民國一一四年度及一一三年度，\r\n所得稅主要組成如下：\r\n以下內容\n'
        result = mark_missing_headings(text)
        self.assertEqual(result.markdown, '\n## 民國一一四年度及一一三年度， 所得稅主要組成如下：\r\n以下內容\n')
        self.assertEqual(result.changes[0].line_number, 2)
        self.assertIn('\r\n', result.changes[0].original)
        self.assertEqual(mark_missing_headings(result.markdown).markdown, result.markdown)

    def test_tables_and_control_markers_are_barriers(self):
        for table in ('<table>\n<tr><td>不處理：</td></tr>\n</table>\n',
                      '| 欄位 |\n| --- |\n| 不處理： |\n'):
            text = table + '<note>\n<!-- Page: 2303_2025_P14 -->\n說明\n如下:\n'
            result = mark_missing_headings(text).markdown
            self.assertEqual(result, table + '<note>\n<!-- Page: 2303_2025_P14 -->\n## 說明 如下:\n')

    def test_blank_lines_appendices_years_and_code_are_preserved(self):
        text = '前一段\n\n說明\n如下：\n\n附表一：長名稱\n2025年度\n```\n不處理：\n```\n'
        result = mark_missing_headings(text).markdown
        self.assertEqual(result, '前一段\n\n## 說明 如下：\n\n#### 附表一：長名稱\n## 2025年度\n```\n不處理：\n```\n')


if __name__ == '__main__':
    unittest.main()
