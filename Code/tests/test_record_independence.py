"""階段輸入以資料內容為準；Record 可用來追溯但不作通行證。"""
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.markdown_processing.process_batch import process_raw_batch
from functions.markdown_processing.tag_batch import tag_processed_batch
from functions.chunking.batch import chunk_tagged_batch


RAW = ('<!-- Page: 2330_2025_P1 -->\n封面\n'
       '<note>\n<!-- Page: 2330_2025_P15 -->\n一、公司沿革\n本公司營業情形。\n- 15 -\n')


class RecordIndependenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = replace(SETTINGS, project_root=Path(self.tmp.name))
        self.name = 'Financial_20261023_20-00-00'
        self.raw_batch = self.settings.markdown_output_dir / self.name
        self.raw_batch.mkdir(parents=True)
        (self.raw_batch / '2025_2330_raw.md').write_text(RAW, encoding='utf-8')

    def test_legacy_raw_without_record_completes_second_stage(self):
        row = process_raw_batch(self.raw_batch, self.settings)[0]
        self.assertEqual(row['status'], 'processed_needs_review')
        self.assertEqual(row['selection_status'], 'unverified_legacy_raw')
        output = Path(row['output_dir'])
        self.assertIn('## 一、公司沿革', (output / '2025_2330_processed.md').read_text(encoding='utf-8'))
        self.assertNotIn('- 15 -', (output / '2025_2330_processed.md').read_text(encoding='utf-8'))

    def test_old_failed_report_is_untouched_and_rerun_uses_new_batch(self):
        target = self.settings.markdown_processed_output_dir / self.name / 'Record'
        target.mkdir(parents=True)
        old = target / '2025_2330_reocrd'
        old.write_text(json.dumps({'status': 'failed', 'source': str(self.raw_batch / '2025_2330_raw.md')}),
                       encoding='utf-8')
        previous = old.read_bytes()
        row = process_raw_batch(self.raw_batch, self.settings)[0]
        self.assertEqual(row['status'], 'processed_needs_review')
        self.assertNotIn('previous_failed_record', row)
        self.assertEqual(old.read_bytes(), previous)
        again = process_raw_batch(self.raw_batch, self.settings)[0]
        self.assertNotEqual(row['output_dir'], again['output_dir'])

    def test_tagged_and_chunk_do_not_need_upstream_reports(self):
        row = process_raw_batch(self.raw_batch, self.settings)[0]
        processed = Path(row['output_dir'])
        (processed / 'Record' / '2025_2330_reocrd').unlink()
        tagged = tag_processed_batch(processed, self.settings)[0]
        self.assertEqual(tagged['status'], 'tagged_needs_review')
        tagged_batch = Path(tagged['output_dir'])
        tagged_text = (tagged_batch / '2025_2330_tagged.md').read_text(encoding='utf-8')
        self.assertTrue(tagged_text.startswith('<!-- TAGGING_VERSION: '))
        (tagged_batch / 'Record' / '2025_2330_reocrd').unlink()
        chunk = chunk_tagged_batch(tagged_batch, self.settings)[0]
        self.assertEqual(chunk['status'], 'chunked_needs_review')
        self.assertTrue((Path(chunk['output_dir']) / '2025_2330_chunk_text-full_table-full.json').is_file())


if __name__ == '__main__':
    unittest.main()
