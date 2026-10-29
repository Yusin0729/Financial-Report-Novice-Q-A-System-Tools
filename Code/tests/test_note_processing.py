import sys
import unittest
from pathlib import Path
from dataclasses import replace
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.markdown_processing.note_processing import process_note_content
from functions.markdown_processing.process_batch_local import process_raw_batch


class NoteScopeTests(unittest.TestCase):
    def test_prefix_preserved_and_all_rules_only_after_marker(self):
        prefix = ('\ufeff<!-- Page: 2303_2025_P4 -->\r\n## 查核意見\r\nA. ' + '長'*30
                  + '\r\n說明：\r\n4\r\n<note>\r\n')
        suffix = '<!-- Page: 2303_2025_P14 -->\r\n2025年度\r\n\r\n說明\r\n如下：\r\n14\r\n'
        result, removed, scope = process_note_content(prefix + suffix)
        self.assertTrue(result.markdown.startswith(prefix))
        self.assertIn('## 2025年度\r\n', result.markdown)
        # 已確認的全文件中文字符間空白清理也會移除冒號合併時的間隔。
        self.assertIn('## 說明如下：\r\n', result.markdown)
        self.assertEqual([r['text'] for r in removed], ['14'])
        self.assertTrue(all(c.line_number > scope['marker_line'] for c in result.changes))
        self.assertEqual(process_note_content(result.markdown)[0].markdown, result.markdown)

    def test_fake_missing_and_duplicate_markers_rejected(self):
        for text in ('無標記', '```\n<note>\n```', '<!--\n<note>\n-->',
                     '<table>\n<note>\n</table>', '正文裡的<note>', '<note>\n<note>\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                process_note_content(text)

    def test_batch_missing_marker_only_saves_failed_record(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = replace(SETTINGS, project_root=Path(folder))
            batch = settings.markdown_output_dir / 'Financial_20261024_18-00-00'
            batch.mkdir(parents=True)
            (batch / '2025_2303_raw.md').write_text('<!-- Page: 2303_2025_P4 -->\n## 查核意見\n', encoding='utf-8')
            row = process_raw_batch(batch, settings)[0]
            self.assertEqual(row['status'], 'failed')
            self.assertIn('<note>', row['error'])
            # 第二階段建立自己的新批次，不再沿用raw批次名稱。
            output = settings.markdown_processed_output_dir / row['batch']
            self.assertFalse((output / '2025_2303_processed.md').exists())
            self.assertTrue((output / 'Record/2025_2303_reocrd').exists())


if __name__ == '__main__':
    unittest.main()
