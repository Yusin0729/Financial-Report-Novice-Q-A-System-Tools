"""驗證已確認門檻、區塊邊界及原文保留；不宣稱實際辨識準確率。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.suspected_tables import detect_suspected_tables, is_numeric_line
from functions.markdown_processing.note_processing import process_note_content
from functions.markdown_processing.mark_headings import mark_missing_headings, TableBoundaryError

NUMBERS = '$10,996\n\n(2,651)\n-2,651\n4.125%\n1,020,226\n'
LONG = '中'*21 + '\n'


class SuspectedTableTests(unittest.TestCase):
    def test_numeric_formats_and_chinese_words_not_numbers(self):
        for value in ('10,996', '$10,996', '(2,651)', '-2,651', '4.125%',
                      ' $ 1,020,226 ', '（２，６５１）', r'\-2,651'):
            self.assertTrue(is_numeric_line(value), value)
        for value in ('114.12.31', '收入10,996', 'USD 10,996', '## 123', '$', '-', ''):
            self.assertFalse(is_numeric_line(value), value)

    def test_short_label_included_and_three_long_lines_excluded(self):
        original = '期初餘額\n' + NUMBERS + LONG + '\n' + LONG + '\n' + LONG
        result, blocks, mapping = detect_suspected_tables(original)
        self.assertEqual(result, '<cannotfindtable>\n期初餘額\n' + NUMBERS + '</cannotfindtable>\n'
                         + LONG + '\n' + LONG + '\n' + LONG)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['stop_reason'], 'three_long_chinese_body_lines')
        self.assertEqual(len(mapping), len(result.splitlines()))
        self.assertEqual(result.replace('<cannotfindtable>\n', '').replace('</cannotfindtable>\n', ''), original)

    def test_short_text_and_money_fragments_count_together(self):
        for original in ('稅前淨利\n\n$\n979,171,324\n稅額\n197,906,699\n',
                         '(\n5,647\n,\n246 )\n( $ 8\n',
                         ('中'*20+'\n')*5):
            result, blocks, _ = detect_suspected_tables(original)
            self.assertEqual(result, '<cannotfindtable>\n'+original+'</cannotfindtable>\n')
            self.assertEqual(blocks[0]['trigger'], '5_consecutive_candidate_lines')

    def test_long_line_resets_initial_streak_and_blanks_do_not_count(self):
        for original in ('項目\n1\n2\n3\n'+LONG+'4\n5\n6\n7\n',
                         '項目\n\n$\n\n(\n\n123\n'):
            self.assertEqual(detect_suspected_tables(original)[0], original)

    def test_only_chinese_count_matters_and_punctuation_no_longer_stops(self):
        text = NUMBERS + ('中文，這是短句。\n' * 3) + ('English words '*30 + '\n') + ('中'*20 + '\n')
        result, blocks, _ = detect_suspected_tables(text)
        self.assertEqual(blocks[0]['stop_reason'], 'end_of_document')
        self.assertIn(('English words '*30), result)

    def test_two_long_lines_do_not_stop_and_short_line_resets_body_streak(self):
        text = NUMBERS + LONG + LONG + '短文字\n' + LONG + LONG
        result, blocks, _ = detect_suspected_tables(text)
        self.assertEqual(blocks[0]['end_line'], len(text.splitlines()))
        self.assertEqual(blocks[0]['stop_reason'], 'end_of_document')

    def test_heading_table_and_page_boundaries_do_not_accumulate(self):
        for barrier in ('## 123\n', '<table>\n1\n2\n3\n4\n5\n</table>\n',
                        '| 欄位 |\n| --- |\n| 123 |\n', '<!-- Page: 2330_2025_P2 -->\n'):
            text = '1\n2\n3\n4\n' + barrier + '5\n6\n7\n8\n'
            self.assertEqual(detect_suspected_tables(text)[0], text)
            text = NUMBERS + barrier
            result, _, _ = detect_suspected_tables(text)
            self.assertIn('</cannotfindtable>\n' + barrier, result)

    def test_note_prefix_page_footer_and_candidate_raw_protection(self):
        prefix = '## 查核意見\n' + NUMBERS + '<note>\n'
        body = '<!-- Page: 2330_2025_P8 -->\n項目\n' + NUMBERS + '1. 不應新增標題\n8\n'
        result, removed, scope = process_note_content(prefix + body)
        self.assertTrue(result.markdown.startswith(prefix))
        self.assertIn('1.不應新增標題\n</cannotfindtable>', result.markdown)
        self.assertNotIn('## 1. 不應新增標題', result.markdown)
        self.assertEqual([item['text'] for item in removed], ['8'])
        report = scope['suspected_table_detection']
        self.assertEqual(report['candidate_count'], 1)
        self.assertEqual(report['candidates'][0]['pdf_pages'], [8])
        self.assertEqual(process_note_content(result.markdown)[0].markdown, result.markdown)

    def test_existing_blocks_idempotent_and_malformed_fail(self):
        text = '<cannotfindtable>\n1. 原文\n' + NUMBERS + '</cannotfindtable>\n'
        self.assertEqual(detect_suspected_tables(text)[0], text)
        self.assertEqual(mark_missing_headings(text).markdown, text)
        for text in ('<cannotfindtable>\n內容', '</cannotfindtable>\n',
                     '<cannotfindtable>\n<cannotfindtable>\n</cannotfindtable>\n'):
            with self.assertRaises(TableBoundaryError):
                detect_suspected_tables(text)

    def test_eof_without_newline_and_changes_reference_original_lines(self):
        text = '項目\r\n' + NUMBERS.rstrip('\n')
        result, blocks, _ = detect_suspected_tables(text)
        self.assertTrue(result.endswith('1,020,226\n</cannotfindtable>\n'))
        self.assertTrue(blocks[0]['added_eol'])
        raw = '<note>\n' + NUMBERS + '## 章節\n一、標題\n'
        result, _, _ = process_note_content(raw)
        change = next(c for c in result.changes if c.original == '一、標題')
        self.assertEqual(change.line_number, len(raw.splitlines()))


if __name__ == '__main__':
    unittest.main()
