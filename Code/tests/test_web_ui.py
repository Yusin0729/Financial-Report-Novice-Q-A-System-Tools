"""本機介面契約測試；不執行 OCR、API 或使用者的財報。"""
import json
import io
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, Mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from functions.web_ui.catalog import catalog, selected_paths
from functions.web_ui.server import make_server
from functions.web_ui.server import App
from functions.web_ui.worker import execute

class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(project_root=Path(self.temp.name))
        self.settings.source_dir.mkdir()
        (self.settings.source_dir / '2025Q4_2330_Financial_Report.pdf').write_bytes(b'test')

    def test_catalog_and_escape(self):
        self.assertEqual(len(catalog(self.settings, 'raw')), 1)
        for ids in [['../other.pdf'], ['missing.pdf'], [], ['x', 'x']]:
            with self.assertRaises(ValueError):
                selected_paths(self.settings, 'raw', ids)

    def test_only_nonempty_valid_batches(self):
        root = self.settings.markdown_output_dir
        for name in ['Record', 'Financial_20261022_12-00-00', 'Financial_20261022_001']:
            (root / name).mkdir(parents=True)
        (root / 'Record/a_raw.md').write_text('x')
        (root / 'Financial_20261022_001/a_raw.md').write_text('x')
        self.assertEqual(catalog(self.settings, 'processed'), [{'id': 'Financial_20261022_001/a_raw.md', 'count': 1}])

    def test_http_token_origin_and_busy(self):
        server = make_server(self.settings)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        page = urlopen(base).read().decode()
        self.assertIn('資料處理工作台', page)
        self.assertIn('id="originalMode"', page)
        self.assertIn('id="parentChildMode"', page)
        self.assertNotIn('__CHUNK_MODE__', page)
        self.assertIn('value="1500"', page)
        self.assertIn('value="300"', page)
        self.assertIn('value="700"', page)
        self.assertIn('id="ocr" checked', page)
        self.assertIn('[hidden]{display:none!important}', page)
        self.assertIn('id="parentRange" type="range" min="1" max="3000"', page)
        self.assertIn('id="thresholdRange" type="range" min="1" max="1500"', page)
        self.assertIn('id="childRange" type="range" min="1" max="1000"', page)
        self.assertLess(page.index('id="parentLimit"'), page.index('id="recursiveThreshold"'))
        self.assertLess(page.index('id="recursiveThreshold"'), page.index('id="childTarget"'))
        self.assertIn('id="statusPanel" class="panel" aria-live="polite" hidden', page)
        self.assertIn('id="cancel" hidden', page)
        self.assertNotIn('__OCR_CHECKED__', page)
        self.assertNotIn('__PARENT_SLIDER_MAX__', page)
        with self.assertRaises(HTTPError) as error:
            urlopen(base + '/api/state')
        self.assertEqual(error.exception.code, 403)
        headers = {'X-UI-Token': server.app.token, 'Content-Type': 'application/json'}
        self.assertIn('raw', json.load(urlopen(Request(base+'/api/catalog', headers=headers))))
        with self.assertRaises(HTTPError):
            urlopen(Request(base+'/api/state', headers={**headers, 'Origin': 'https://example.com'}))
        server.app.busy = True
        with self.assertRaises(HTTPError):
            urlopen(Request(base+'/api/shutdown', data=b'{}', headers=headers))
        with self.assertRaises(ValueError):
            server.app.start({})
        server.app.busy = False
        self.assertFalse(server.app.closing)

    def test_worker_four_stages_and_partial_failure(self):
        for stage, root, suffix, function, status in [
            ('processed', self.settings.markdown_output_dir, 'raw', 'process_raw_batch', 'processed_toc_failed'),
            ('tagged', self.settings.markdown_processed_output_dir, 'processed', 'tag_processed_batch', 'tagged_needs_review'),
            ('chunk', self.settings.markdown_tagged_output_dir, 'tagged', 'chunk_tagged_batch', 'chunked_needs_review')]:
            batch = root / 'Financial_20261022_001'
            batch.mkdir(parents=True)
            (batch / f'2025_2330_{suffix}.md').write_text('test')
            events = []
            with patch('main.' + function, return_value=[{'status': status, 'source': 'file.md', 'elapsed_seconds': 1.25}]) as mock:
                execute({'stage': stage, 'ids': [f'{batch.name}/2025_2330_{suffix}.md'], 'ocr': False}, self.settings, events.append)
                self.assertEqual(mock.call_args.args[0], batch)
                self.assertEqual(mock.call_args.kwargs['source_files'], [f'2025_2330_{suffix}.md'])
            result = next(e['result'] for e in events if 'result' in e)
            self.assertEqual(result['elapsed_seconds'], 1.25)
            expected = 'completed_with_errors' if stage == 'processed' else 'completed'
            self.assertEqual(events[-1]['state'], expected)
        events = []
        with patch('main.run_markdown', return_value={'status': 'converted_needs_review'}) as mock:
            execute({'stage': 'raw', 'ids': [catalog(self.settings, 'raw')[0]['id']], 'ocr': True}, self.settings, events.append)
            self.assertTrue(mock.call_args.args[1].ocr_enabled)
            self.assertIsNotNone(mock.call_args.kwargs['batch_dir'])
        self.assertEqual(events[-1]['state'], 'completed')
        self.assertGreaterEqual(next(e['result'] for e in events if 'result' in e)['elapsed_seconds'], 0)
        events = []
        with patch('main.run_markdown', side_effect=ValueError('test failure')):
            execute({'stage': 'raw', 'ids': [catalog(self.settings, 'raw')[0]['id']], 'ocr': False}, replace(self.settings, export_enabled=False), events.append)
        result = next(e['result'] for e in events if 'result' in e)
        self.assertEqual(result['status'], 'failed')
        self.assertGreaterEqual(result['elapsed_seconds'], 0)

    def test_existing_output_not_reported_as_success(self):
        events = []
        with patch('main.run_markdown', side_effect=FileExistsError('existing')):
            execute({'stage': 'raw', 'ids': [catalog(self.settings, 'raw')[0]['id']], 'ocr': False}, self.settings, events.append)
        self.assertEqual(events[-1]['state'], 'completed_with_errors')
        self.assertIn('未覆寫', next(e['result']['message'] for e in events if 'result' in e))

    def test_worker_exit_and_event_protocol(self):
        for exit_code, expected in [(0, 'completed'), (1, 'failed')]:
            app = App(self.settings)
            app.busy = True
            app.state = {'state': 'running', 'results': []}
            process = Mock(stdin=io.StringIO(), stdout=io.StringIO(
                '{"result":{"name":"test","status":"converted_needs_review"}}\n'
                '{"state":"completed"}\n'))
            process.wait.return_value = exit_code
            with patch('functions.web_ui.server.subprocess.Popen', return_value=process),patch('functions.web_ui.server.ProcessScope'):
                app.run({'stage': 'raw', 'ids': [catalog(self.settings,'raw')[0]['id']], 'ocr': False})
            self.assertEqual(app.state['state'], expected)
            self.assertEqual(len(app.state['results']), 1)
            self.assertFalse(app.busy)

    def test_processed_does_not_require_gemini_ack(self):
        batch = self.settings.markdown_output_dir / 'Financial_20261022_001'
        batch.mkdir(parents=True)
        (batch / '2025_2330_raw.md').write_text('test')
        app = App(self.settings)
        with patch('functions.web_ui.server.threading.Thread') as worker:
            app.start({'stage': 'processed', 'ids': [batch.name+'/2025_2330_raw.md'], 'ocr': False})
        self.assertTrue(app.busy)
        worker.return_value.start.assert_called_once()

if __name__ == '__main__':
    unittest.main()
