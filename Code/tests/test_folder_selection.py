"""資料夾遞迴與檔案子集，實際走本機三階段，未執行OCR或API。"""
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from functions.web_ui.catalog import catalog, selected_paths
from functions.web_ui.worker import execute
from functions.markdown_processing.process_batch_local import process_raw_batch
from functions.markdown_processing.tag_batch import tag_processed_batch
from functions.chunking.batch import chunk_tagged_batch


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(project_root=Path(self.temp.name))
        self.batch = 'Financial_20261023_12-30-00'

    def test_catalog_lists_nested_files_at_all_stages_and_excludes_record(self):
        cases = [('raw', self.settings.source_dir, 'report.pdf'),
                 ('processed', self.settings.markdown_output_dir / self.batch, '2025_2330_raw.md'),
                 ('tagged', self.settings.markdown_processed_output_dir / self.batch, '2025_2330_processed.md'),
                 ('chunk', self.settings.markdown_tagged_output_dir / self.batch, '2025_2330_tagged.md')]
        for stage, root, filename in cases:
            nested = root / '分組' / '子資料夾'
            nested.mkdir(parents=True)
            (nested / filename).write_text('test', encoding='utf-8')
            if stage != 'raw':
                (root / 'Record').mkdir()
                (root / 'Record' / filename).write_text('not a source')
            rows = catalog(self.settings, stage)
            self.assertEqual(len(rows), 1)
            self.assertIn('分組/子資料夾/'+filename, rows[0]['id'])
            self.assertEqual(selected_paths(self.settings, stage, [rows[0]['id']]), [nested/filename])
            for bad in ['../'+filename, rows[0]['id']+'/..', filename]:
                with self.assertRaises(ValueError):
                    selected_paths(self.settings, stage, [bad])

    def test_three_real_stages_only_process_selected_file_not_unselected_collision(self):
        batch = self.settings.markdown_output_dir / self.batch
        (batch / '分組').mkdir(parents=True)
        source = batch / '分組/2025_2330_raw.md'
        source.write_text('<note>\n<!-- Page: 2330_2025_P15 -->\n一、公司沿革\n公司正文\n', encoding='utf-8')
        cases = [('processed', process_raw_batch, self.settings.markdown_output_dir, 'raw',
                  self.settings.markdown_processed_output_dir, 'processed'),
                 ('tagged', tag_processed_batch, self.settings.markdown_processed_output_dir, 'processed',
                  self.settings.markdown_tagged_output_dir, 'tagged'),
                 ('chunk', chunk_tagged_batch, self.settings.markdown_tagged_output_dir, 'tagged',
                  self.settings.markdown_chunk_output_dir, 'chunk')]
        for stage, fn, root, role, output, output_role in cases:
            if stage != 'processed':
                batch = Path(records[0]['output_dir'])
            else:
                batch = root/self.batch
            (batch/f'2025_2379_{role}.md').write_text('unselected invalid content', encoding='utf-8')
            target = output/self.batch
            if stage == 'chunk':
                target = target/self.settings.chunking.mode
            target.mkdir(parents=True, exist_ok=True)
            blocked = target/f'2025_2379_{output_role}.md'
            blocked.write_text('existing unselected output', encoding='utf-8')
            relative = '分組/2025_2330_raw.md' if stage == 'processed' else f'2025_2330_{role}.md'
            records = fn(batch, self.settings, source_files=[relative])
            self.assertEqual(len(records), 1)
            self.assertIn(records[0]['status'], ('processed_needs_review','tagged_needs_review','chunked_needs_review'))
            self.assertTrue((Path(records[0]['output_dir'])/f'2025_2330_{output_role}.md').is_file())
            self.assertEqual(blocked.read_text(encoding='utf-8'), 'existing unselected output')
            self.assertFalse((target/'Record/2025_2379_reocrd').exists())

    def test_duplicate_output_identity_rejected_before_worker(self):
        batch = self.settings.markdown_output_dir/self.batch
        for folder in ['甲','乙']:
            (batch/folder).mkdir(parents=True)
            (batch/folder/'2025_2330_raw.md').write_text('test')
        ids = [x['id'] for x in catalog(self.settings,'processed')]
        with self.assertRaisesRegex(ValueError, '重複'):
            selected_paths(self.settings,'processed',ids)

    def test_worker_passes_each_nested_file_to_existing_core_and_counts_files(self):
        batch = self.settings.markdown_output_dir/self.batch
        (batch/'分組').mkdir(parents=True)
        for stock in ['2330','2379']:
            (batch/'分組'/f'2025_{stock}_raw.md').write_text('test')
        ids = [x['id'] for x in catalog(self.settings,'processed')]
        events=[]
        with patch('main.process_raw_batch', return_value=[{'status':'processed_needs_review'}]) as core:
            execute({'stage':'processed','ids':ids,'ocr':False},self.settings,events.append)
        self.assertEqual(core.call_count,2)
        self.assertEqual(core.call_args_list[0].kwargs['source_files'], ['分組/2025_2330_raw.md'])
        self.assertEqual(core.call_args_list[1].kwargs['source_files'], ['分組/2025_2379_raw.md'])
        self.assertEqual(events[-1]['state'],'completed')
        self.assertEqual([e['completed'] for e in events if 'completed' in e][-1],2)

    def test_nested_processed_does_not_use_adjacent_toc_json(self):
        from test_comment_tagging import toc_fixture
        batch=self.settings.markdown_processed_output_dir/self.batch
        nested=batch/'分組'
        nested.mkdir(parents=True)
        (nested/'2025_2330_processed.md').write_text(
            '<!-- Page: 2330_2025_P1 -->\n## 一、公司沿革\n正文\n<!-- Page: 2330_2025_P3 -->\n正文\n', encoding='utf-8')
        (nested/'2025_2330_tablerefer.json').write_text(json.dumps(toc_fixture(),ensure_ascii=False),encoding='utf-8')
        records=tag_processed_batch(batch,self.settings,source_files=['分組/2025_2330_processed.md'])
        self.assertEqual(records[0]['status'],'tagged_needs_review')
        self.assertNotIn('toc_source', records[0])
        self.assertNotIn('MAIN_TITLE:', records[0]['result'].markdown)
        self.assertFalse(records[0]['temporary_fallback'])


if __name__=='__main__':
    unittest.main()
