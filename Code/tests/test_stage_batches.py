"""每次執行的新批次、跨來源合併與取消；暫存資料，不呼叫模型。"""
import json
import re
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from functions.web_ui.catalog import catalog, selected_paths
from functions.web_ui.worker import execute
from functions.experiments.export_output import stage_output_batch
from functions.experiments.cancelled_run import OutputSession
from functions.experiments.output_ownership import output_observer, exclusive_output
from functions.markdown_processing.process_batch_local import process_raw_batch
from Code_2.config.embedding import Settings as EmbeddingSettings
from Code_2.functions.embedding.batch import prepare_batch


class StageBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(project_root=Path(self.temp.name))

    def source(self, stock, batch='Financial_20261025_10-00-00'):
        path = self.settings.markdown_output_dir/batch/f'2025_{stock}_raw.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'<note>\n<!-- Page: {stock}_2025_P15 -->\n一、公司沿革\n公司正文。\n', encoding='utf-8')
        return path

    def test_multi_source_batches_combine_once_and_flow_to_next_stage(self):
        self.source('2330')
        self.source('2303', 'Financial_20261025_11-00-00')
        outputs = {}
        for stage in ('processed', 'tagged', 'chunk'):
            events = []
            ids = [row['id'] for row in catalog(self.settings, stage)]
            self.assertEqual(len(ids), 2)
            execute({'stage':stage, 'ids':ids, 'ocr':False}, self.settings, events.append)
            self.assertEqual(events[-1]['state'], 'completed')
            batches = [Path(e['output']) for e in events if 'output' in e]
            self.assertEqual(len(batches), 1)
            output = batches[0]
            self.assertRegex(output.name, rf'^Financial_{stage}_\d{{8}}_\d{{2}}-\d{{2}}-\d{{2}}$')
            outputs[stage] = output
            target = output/self.settings.chunking.mode if stage == 'chunk' else output
            for stock in ('2330', '2303'):
                self.assertTrue((target/f'2025_{stock}_{stage}.md').is_file())
                record = json.loads((target/'Record'/f'2025_{stock}_reocrd').read_text(encoding='utf-8'))
                self.assertEqual(record['batch'], output.name)
                self.assertNotEqual(record['source_batch'], output.name)
                self.assertIsNone(record.get('source_record_issue')) if stage != 'processed' else None
        # 下游只核對新批次名稱可讀，不執行embedding或建立真實索引。
        rows = prepare_batch(outputs['chunk'], EmbeddingSettings(project_root=Path(self.temp.name)))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['status'] == 'prepared_needs_review' for row in rows))

    def test_same_source_rerun_creates_new_batch_preserving_old_files(self):
        source = self.source('2330')
        first = process_raw_batch(source.parent, self.settings)[0]
        path = Path(first['output_dir'])/'2025_2330_processed.md'
        before = path.read_bytes()
        second = process_raw_batch(source.parent, self.settings)[0]
        self.assertNotEqual(first['output_dir'], second['output_dir'])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual((Path(second['output_dir'])/path.name).read_bytes(), before)

    def test_cross_batch_duplicate_identity_rejected_before_output(self):
        self.source('2330')
        self.source('2330', 'Financial_20261025_11-00-00')
        ids = [row['id'] for row in catalog(self.settings, 'processed')]
        with self.assertRaisesRegex(ValueError, '重複'):
            selected_paths(self.settings, 'processed', ids)
        self.assertFalse(self.settings.markdown_processed_output_dir.exists())

    def test_cancel_tracks_new_output_and_preserves_prior_source_batch(self):
        source = self.source('2330')
        output = stage_output_batch(self.settings, 'processed')
        session = OutputSession(self.settings, 'processed', [source], 'new-batch')
        session.set_raw_batch(str(output))
        session.begin(0)
        path = output/'2025_2330_processed.md'
        with output_observer(session.create):
            with exclusive_output(path, 'xb') as stream:
                stream.write(b'partial')
        _, issues = session.cancel()
        self.assertFalse(issues)
        self.assertFalse(path.exists())
        self.assertTrue(source.is_file())
        record = json.loads((output/'Record/2025_2330_reocrd').read_text(encoding='utf-8'))
        self.assertEqual(record['status'], 'cancelled')

    def test_no_export_creates_no_batch(self):
        source = self.source('2330')
        events = []
        execute({'stage':'processed', 'ids':[source.relative_to(self.settings.markdown_output_dir).as_posix()],
                 'ocr':False}, replace(self.settings, export_enabled=False), events.append)
        self.assertEqual(events[-1]['state'], 'completed')
        self.assertFalse(self.settings.markdown_processed_output_dir.exists())

    def test_same_second_waits_without_suffix_or_overwrite(self):
        local = datetime(2026,10,25,16,1,30,500000,tzinfo=timezone(timedelta(hours=8)))
        first = self.settings.markdown_processed_output_dir/'Financial_processed_20261025_16-01-30'
        first.mkdir(parents=True)
        with patch('functions.experiments.export_output.datetime') as clock, patch('time.sleep') as sleep:
            clock.now.side_effect = [local, local+timedelta(seconds=1)]
            output = stage_output_batch(self.settings, 'processed')
        self.assertEqual(output.name, 'Financial_processed_20261025_16-01-31')
        sleep.assert_called_once()
        self.assertTrue(first.is_dir())


if __name__ == '__main__':
    unittest.main()
