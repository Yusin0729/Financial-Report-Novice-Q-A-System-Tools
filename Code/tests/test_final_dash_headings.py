"""末段重查不推翻###，並沿用標點、長度與區域保護。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.mark_headings import recheck_dash_number_headings
from functions.markdown_processing.note_processing import process_note_content


class FinalDashTests(unittest.TestCase):
    def test_eligible_numbered_line_preserves_original_spaces(self):
        for text in ('- 1. 現金', '- 1 2 . 現 金', '- 1. '+'甲 '*20):
            self.assertEqual(recheck_dash_number_headings(text).markdown, '## '+text[2:])
        text = '- 1. 方法：\n'
        self.assertEqual(recheck_dash_number_headings(text).markdown, '## '+text[2:])

    def test_rejects_punctuation_length_numeric_and_already_marked(self):
        for text in ('- 1. 說明。', '- 1. '+'甲'*21, '- 4.375%', '- 1.',
                     '### - 1. 現金', '- A. 英文', '普通內文'):
            self.assertEqual(recheck_dash_number_headings(text).markdown, text)

    def test_existing_numbered_headings_drop_bullet_only(self):
        for text in ('## - 1. 現 金', '## - (1) 方法', '##- （ 1 ） 方法'):
            result = recheck_dash_number_headings(text)
            self.assertEqual(result.markdown, text.replace('- ', '', 1))
        protected = '<table>\n## - 1. 表內\n</table>\n### - 1. 條列\n'
        self.assertEqual(recheck_dash_number_headings(protected).markdown, protected)

    def test_protected_content_unchanged(self):
        for text in ('<table>\n- 1. 現金\n</table>', '```\n- 1. 現金\n```',
                     '<cannotfindtable>\n- 1. 現金\n</cannotfindtable>', '    - 1. 現金'):
            self.assertEqual(recheck_dash_number_headings(text).markdown, text)

    def test_pipeline_keeps_note_prefix_and_classified_lists(self):
        prefix = '- 1. 查核\n<note>\n'
        result, _, scope = process_note_content(prefix+'- 1. 第一項。\n- 2. 第二項。\n')
        self.assertTrue(result.markdown.startswith(prefix))
        self.assertIn('### - 1. 第一項。\n### - 2. 第二項。', result.markdown)
        self.assertEqual(scope['final_dash_number_recheck']['changed_count'], 0)


if __name__ == '__main__':
    unittest.main()
