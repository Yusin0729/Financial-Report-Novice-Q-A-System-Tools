"""第二階段整體串接測試；真實兩頁PDF、本機補標題、模擬Gemini，無網路。"""
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.markdown_processing.process_batch import process_raw_batch
from test_toc import make_pdf, response, main_fixture


class ProcessBatchTests(unittest.TestCase):
    def test_503_attempts_saved_on_success_exhaustion_and_wait_interrupt(self):
        for mode in ('success', 'exhausted', 'interrupted'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                settings, batch, _ = self.setup_batch(tmp, ('2317', '2330'))
                reply = MagicMock()
                reply.__enter__.return_value.read.return_value = json.dumps(response()).encode()
                opener = MagicMock()
                failures = 4 if mode == 'exhausted' else 1
                opener.open.side_effect = [HTTPError('url', 503, 'busy', {}, None) for _ in range(failures)] + [reply, reply]
                with patch.dict('os.environ', {'GEMINI_API_KEY': 'FAKE_TEST_KEY'}), \
                     patch('functions.integrations.gemini_toc.build_opener', return_value=opener), \
                     patch('functions.integrations.gemini_toc.time.sleep',
                           side_effect=KeyboardInterrupt if mode == 'interrupted' else None):
                    results = process_raw_batch(batch, settings)
                out = settings.markdown_processed_output_dir / batch.name
                record = json.loads((out / 'Record/2025_2317_reocrd').read_text(encoding='utf-8'))
                expected = {'success': 'processed_needs_review', 'exhausted': 'processed_toc_failed', 'interrupted': 'interrupted'}[mode]
                self.assertEqual(record['status'], expected)
                self.assertEqual(len(record['gemini_attempts']), 2 if mode == 'success' else failures)
                self.assertTrue((out / '2025_2317_processed.md').is_file())
                self.assertEqual((out / '2025_2317_tablerefer.json').exists(), mode == 'success')
                self.assertEqual(len(results), 1 if mode == 'interrupted' else 2)
                if mode != 'interrupted':
                    self.assertEqual(results[1]['status'], 'processed_needs_review')
                self.assertNotIn('FAKE_TEST_KEY', json.dumps(record))

    def setup_batch(self, folder, stocks=('2330',)):
        settings = replace(SETTINGS, project_root=Path(folder))
        batch = settings.markdown_output_dir / 'Financial_20261022_16-01-35'
        (batch / 'Financial_Table').mkdir(parents=True)
        records = batch / 'Record'
        records.mkdir()
        text = '<!-- PDF_PAGE: 1 -->\n會計師報告\n完整前段內文。\n- 1 -\n<!-- PDF_PAGE: 2 -->\n一、公司沿革\n說明。\n<table><tr><td>1. 表格原文</td></tr></table>\n'
        for stock in stocks:
            prefix = f'2025_{stock}'
            (batch / f'{prefix}_raw.md').write_bytes(text.encode('utf-8'))
            table = batch / 'Financial_Table' / f'{prefix}_table.pdf'
            table.write_bytes(make_pdf(2))
            origin = {'batch_dir': str(batch), 'status': 'converted_needs_review',
                      'source': {'sha256': 'a' * 64, 'unchanged': True, 'pdf_page_count': 85},
                      'table_pdf': str(table), 'table_pdf_sha256': hashlib.sha256(table.read_bytes()).hexdigest(),
                      'table_source_pages': [2, 3]}
            (records / f'{prefix}_reocrd').write_text(json.dumps(origin), encoding='utf-8')
        return settings, batch, text

    def test_success_preserves_front_and_table_and_names_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, text = self.setup_batch(tmp)
            with patch('functions.markdown_processing.process_batch.generate_toc', return_value=response()) as api:
                results = process_raw_batch(batch, settings)
            api.assert_called_once()
            self.assertEqual(api.call_args.args[0].source_pages, (2, 3))
            out = settings.markdown_processed_output_dir / batch.name
            md = (out / '2025_2330_processed.md').read_text(encoding='utf-8')
            self.assertEqual(md, text.replace('一、公司沿革', '## 一、公司沿革').replace('- 1 -\n', ''))
            self.assertEqual((batch / '2025_2330_raw.md').read_bytes(), text.encode('utf-8'))
            toc = json.loads((out / '2025_2330_tablerefer.json').read_text(encoding='utf-8'))
            self.assertEqual(toc['entries'], main_fixture()['entries'])
            record = json.loads((out / 'Record' / '2025_2330_reocrd').read_text(encoding='utf-8'))
            self.assertFalse((settings.markdown_processed_output_dir / 'Record').exists())
            self.assertEqual(record['usage']['promptTokenCount'], 123)
            self.assertEqual(record['removed_page_lines'], [{'source_line': 4, 'text': '- 1 -'}])
            self.assertEqual(results[0]['status'], 'processed_needs_review')
            self.assertEqual(Path(results[0]['origin_record']), batch / 'Record' / '2025_2330_reocrd')
            with patch('functions.markdown_processing.process_batch.generate_toc') as api:
                with self.assertRaises(FileExistsError):
                    process_raw_batch(batch, settings)
                api.assert_not_called()

    def test_new_record_preferred_and_legacy_fallback_requires_matching_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, _ = self.setup_batch(tmp)
            local = batch / 'Record' / '2025_2330_reocrd'
            legacy = settings.markdown_output_dir / 'Record' / local.name
            legacy.parent.mkdir()
            legacy.write_text('old invalid JSON must not be read when local exists', encoding='utf-8')
            no_export = replace(settings, export_enabled=False)
            with patch('functions.markdown_processing.process_batch.generate_toc', return_value=response()):
                results = process_raw_batch(batch, no_export)
            self.assertEqual(results[0]['status'], 'processed_needs_review')
            self.assertEqual(Path(results[0]['origin_record']), local)
            # 測試fixture移到舊位置，驗證舊資料仍可讀。
            legacy.write_bytes(local.read_bytes())
            local.unlink()
            with patch('functions.markdown_processing.process_batch.generate_toc', return_value=response()):
                results = process_raw_batch(batch, no_export)
            self.assertEqual(results[0]['status'], 'processed_needs_review')
            self.assertEqual(Path(results[0]['origin_record']), legacy)
            data = json.loads(legacy.read_text(encoding='utf-8'))
            data['batch_dir'] = str(batch.with_name('Financial_20261022_16-02-35'))
            legacy.write_text(json.dumps(data), encoding='utf-8')
            with patch('functions.markdown_processing.process_batch.generate_toc') as api:
                results = process_raw_batch(batch, no_export)
                api.assert_not_called()
            self.assertEqual(results[0]['status'], 'processed_toc_failed')
            self.assertIn('不屬於此批次', results[0]['error'])

    def test_api_failure_keeps_markdown_and_continues_other_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, _ = self.setup_batch(tmp, ('2317', '2330'))
            with patch('functions.markdown_processing.process_batch.generate_toc', side_effect=[RuntimeError('Gemini HTTP 429'), response()]) as api:
                results = process_raw_batch(batch, settings)
            self.assertEqual(api.call_count, 2)  # 每份一次，不重試失敗文件。
            self.assertEqual([r['status'] for r in results], ['processed_toc_failed', 'processed_needs_review'])
            out = settings.markdown_processed_output_dir / batch.name
            self.assertTrue((out / '2025_2317_processed.md').is_file())
            self.assertNotIn('\n- 1 -\n', (out / '2025_2317_processed.md').read_text(encoding='utf-8'))
            self.assertEqual(len(results[0]['removed_page_lines']), 1)
            self.assertFalse((out / '2025_2317_tablerefer.json').exists())
            self.assertIn('429', results[0]['error'])

    def test_incomplete_or_truncated_response_never_writes_success_json(self):
        unreadable = main_fixture()
        unreadable['pages'][1].update(classification='unreadable', issues=['看不清楚'])
        empty = main_fixture()
        empty['entries'] = []
        for page in empty['pages']:
            page['classification'] = 'not_toc'
        for reply in (response(unreadable), response(reason='MAX_TOKENS'), response(empty)):
            with self.subTest(reply=reply), tempfile.TemporaryDirectory() as tmp:
                settings, batch, _ = self.setup_batch(tmp)
                with patch('functions.markdown_processing.process_batch.generate_toc', return_value=reply):
                    results = process_raw_batch(batch, settings)
                out = settings.markdown_processed_output_dir / batch.name
                self.assertTrue((out / '2025_2330_processed.md').exists())
                self.assertFalse((out / '2025_2330_tablerefer.json').exists())
                self.assertEqual(results[0]['status'], 'processed_toc_failed')

    def test_tampered_pdf_does_not_call_api_but_keeps_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, _ = self.setup_batch(tmp)
            (batch / 'Financial_Table' / '2025_2330_table.pdf').write_bytes(b'changed')
            with patch('functions.markdown_processing.process_batch.generate_toc') as api:
                results = process_raw_batch(batch, settings)
            api.assert_not_called()
            self.assertEqual(results[0]['status'], 'processed_toc_failed')

    def test_interrupt_retains_headings_stops_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, _ = self.setup_batch(tmp, ('2317', '2330'))
            with patch('functions.markdown_processing.process_batch.generate_toc', side_effect=KeyboardInterrupt) as api:
                results = process_raw_batch(batch, settings)
            api.assert_called_once()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['status'], 'interrupted')
            self.assertTrue((settings.markdown_processed_output_dir / batch.name / '2025_2317_processed.md').exists())

    def test_no_export_returns_memory_without_processed_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, _ = self.setup_batch(tmp)
            with patch('functions.markdown_processing.process_batch.generate_toc', return_value=response()):
                results = process_raw_batch(batch, replace(settings, export_enabled=False))
            self.assertIsNotNone(results[0]['result'])
            self.assertIsNotNone(results[0]['toc_result'])
            self.assertFalse(settings.markdown_processed_output_dir.exists())


if __name__ == '__main__':
    unittest.main()
