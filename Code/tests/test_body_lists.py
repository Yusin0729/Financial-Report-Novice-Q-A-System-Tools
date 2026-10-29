"""條列回查與邊界的行為測試；不載入OCR／外部模型。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.body_lists import mark_body_lists
from functions.markdown_processing.note_processing import process_note_content


class BodyListTests(unittest.TestCase):
    def test_adjacent_plain_items_ignore_blank_and_keep_bullet(self):
        text = '- (1) 第一項；\n\n- (2) 第二項。\n'
        out, _, _ = mark_body_lists(text)
        self.assertEqual(out, '### - (1) 第一項；\n\n### - (2) 第二項。\n')
        self.assertEqual(mark_body_lists(out)[0], out)

    def test_missing_middle_heading_and_inner_letter(self):
        text = 'a. 第一項。\n## 1. b. 第二項\nc. 第三項。\n'
        out, changes, report = mark_body_lists(text)
        self.assertEqual(len(changes), 3)
        self.assertIn('### 1. b. 第二項', out)
        self.assertEqual(report['gaps'], [])

    def test_first_heading_requires_colon_and_plain_seed(self):
        text = '## 說明：\n\n## 1. 第一項\n2. 第二項。\n'
        self.assertEqual(mark_body_lists(text)[0],
                         '## 說明：\n\n### 1. 第一項\n### 2. 第二項。\n')
        no_colon = text.replace('說明：', '說明')
        self.assertEqual(mark_body_lists(no_colon)[0], no_colon)
        all_headings = text.replace('2. 第二項。', '## 2. 第二項')
        self.assertEqual(mark_body_lists(all_headings)[0], all_headings)

    def test_last_heading_checked_but_unrelated_heading_stops(self):
        text = 'A. 第一項。\nB. 第二項。\n## C. 第三項\n## 新章節\nD. 其他。\n'
        out, _, _ = mark_body_lists(text)
        self.assertIn('### C. 第三項\n## 新章節\nD. 其他。', out)

    def test_colon_group_continues_across_prose(self):
        text = '## 說明：\n1. 第一項。\n一段解釋。\n2. 第二項。\n'
        out, changes, _ = mark_body_lists(text)
        self.assertEqual(len(changes), 2)
        self.assertIn('一段解釋。\n### 2.', out)

    def test_gaps_report_without_fabrication(self):
        out, _, report = mark_body_lists('a. 甲。\nc. 丙。\n')
        self.assertEqual(out, '### a. 甲。\n### c. 丙。\n')
        self.assertEqual(report['gaps'][0]['missing_ordinals'], [2])

    def test_table_candidate_page_and_code_are_boundaries(self):
        for boundary in ('<table>\n2. 表內\n</table>\n',
                         '<cannotfindtable>\n2. 候選\n</cannotfindtable>\n',
                         '| 欄 |\n| --- |\n| 2 |\n',
                         '<!-- Page: 2330_2024_P2 -->\n', '```\n2. 程式碼\n```\n'):
            text = '1. 第一項。\n'+boundary+'2. 第二項。\n'
            self.assertEqual(mark_body_lists(text)[0], text)
        text = '## 說明：\n## 1.你好\n<table><tr><td>資料</td></tr></table>\n'
        self.assertEqual(mark_body_lists(text)[0], text)

    def test_number_family_case_and_pure_numbers_not_mixed(self):
        for text in ('a. 甲。\nB. 乙。\n', '1. 甲。\n(2) 乙。\n', '4.375%\n5.375%\n'):
            self.assertEqual(mark_body_lists(text)[0], text)

    def test_pipeline_note_scope_and_source_mapping_after_colon_merge(self):
        prefix = 'A. 查核。\nB. 查核。\n<note>\n'
        body = '說明\n如下：\nA. 第一項。\n## B. 第二項\nC. 第三項。\n'
        out, _, scope = process_note_content(prefix+body)
        self.assertTrue(out.markdown.startswith(prefix))
        self.assertIn('### B. 第二項', out.markdown)
        changes = [c for c in out.changes if c.reason == 'body_list:triple_hash']
        self.assertEqual([c.line_number for c in changes], [6, 7, 8])
        self.assertEqual(scope['body_list_classification']['changed_count'], 3)
        self.assertEqual(process_note_content(out.markdown)[0].markdown, out.markdown)


if __name__ == '__main__':
    unittest.main()
