"""實際暫存批次→兩模式MD/JSON→Code_2前處理／載入，無API或模型。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from config.settings import Settings
from functions.chunking.batch import chunk_tagged_batch
from functions.markdown_processing.comment_tagging import tag_comments
from schemas import TaggingMetadata
from functions.web_ui.request_settings import request_settings
from Code_2.config.embedding import Settings as EmbeddingSettings
from Code_2.functions.embedding.batch import prepare_batch
from Code_2.functions.embedding.load_prepared import prepared_sources, load_prepared
from Code_2.functions.embedding.paths import batch_location
from Code_2.functions.web.service import batch_names


class ChunkModeIOTests(unittest.TestCase):
    def test_two_modes_export_without_collision_and_code2_keeps_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(project_root=Path(temp))
            name = 'Financial_20261025_18-00-00'
            batch = settings.markdown_tagged_output_dir/name
            batch.mkdir(parents=True)
            raw = '<note>\n<!-- Page: 2330_2025_P15 -->\n## 一、政策\n' + ('甲'*400+'\n\n')*2
            tagged = tag_comments(raw,None,TaggingMetadata(report_year='2025',stock_code='2330')).markdown
            source = batch/'2025_2330_tagged.md'
            source.write_text(tagged,encoding='utf-8')
            name = 'Financial_chunk_20261025_18-00-00'
            output_batch = settings.markdown_chunk_output_dir/name
            for mode in ('original','parent_child'):
                current = replace(settings,chunking=replace(settings.chunking,mode=mode))
                record = chunk_tagged_batch(batch,current,output_batch=output_batch)[0]
                self.assertEqual(record['status'],'chunked_needs_review')
                target = settings.markdown_chunk_output_dir/name/mode
                suffix = '_700' if mode == 'parent_child' else ''
                doc = json.loads((target/f'2025_2330_chunk{suffix}.json').read_text(encoding='utf-8'))
                self.assertTrue((target/f'2025_2330_chunk{suffix}.md').is_file())
                self.assertEqual(doc['chunking']['mode'],mode)
                self.assertEqual(doc['schema_version'],'financial-chunks/5.0')
                with self.assertRaises(FileExistsError):
                    chunk_tagged_batch(batch,current,output_batch=output_batch)
            self.assertEqual(source.read_text(encoding='utf-8'),tagged)
            second = EmbeddingSettings(project_root=Path(temp))
            rows = prepare_batch(second.input_dir/name,second)
            self.assertEqual(len(rows),2)
            self.assertTrue(all(r['status']=='prepared_needs_review' for r in rows))
            paths = prepared_sources(second.output_dir/name,second)
            self.assertEqual(len(paths),2)
            for path in paths:
                doc,_,origin = load_prepared(path)
                self.assertEqual(doc['chunking']['mode'],path.parent.name)
                self.assertIsNone(origin.get('source_record_issue'))
            self.assertIn(name+'/original',batch_names(second.input_dir))
            self.assertIn(name+'/parent_child',batch_names(second.output_dir))

    def test_parent_limits_export_together_and_keep_legacy_preparation_readable(self):
        from functions.web_ui.catalog import catalog
        with tempfile.TemporaryDirectory() as temp:
            settings=Settings(project_root=Path(temp))
            name='Financial_tagged_20261026_18-00-00'
            batch=settings.markdown_tagged_output_dir/name
            batch.mkdir(parents=True)
            raw='<note>\n<!-- Page: 2330_2025_P15 -->\n## 一、政策\n'+'甲'*1000+'\n'
            tagged=tag_comments(raw,None,TaggingMetadata(report_year='2025',stock_code='2330')).markdown
            (batch/'2025_2330_tagged.md').write_text(tagged,encoding='utf-8')
            output=settings.markdown_chunk_output_dir/'Financial_chunk_20261026_18-00-00'
            for limit in (700,1000):
                current=replace(settings,chunking=replace(settings.chunking,mode='parent_child',recursive_threshold=limit))
                result=chunk_tagged_batch(batch,current,output_batch=output)[0]
                self.assertEqual(result['status'],'chunked_needs_review')
                folder=output/'parent_child'
                self.assertTrue((folder/f'2025_2330_chunk_{limit}.json').is_file())
                self.assertTrue((folder/f'2025_2330_chunk_{limit}.md').is_file())
                self.assertTrue((folder/'Record'/f'2025_2330_{limit}_reocrd').is_file())
            self.assertEqual(len(catalog(settings,'embed')),2)
            # 寬鬆glob仍不得把錯誤尾碼或備份檔列成可建庫來源。
            (output/'parent_child'/'2025_2330_chunk_backup.json').write_text('{}',encoding='utf-8')
            self.assertEqual(len(catalog(settings,'embed')),2)
            (output/'parent_child'/'2025_2330_chunk_backup.json').unlink()
            second=EmbeddingSettings(project_root=Path(temp))
            prepared=prepare_batch(output,second)
            self.assertEqual([r['status'] for r in prepared],['prepared_needs_review']*2)
            paths=prepared_sources(second.output_dir/output.name,second)
            self.assertEqual(len(paths),2)
            limits=set()
            for path in paths:
                doc,_,record=load_prepared(path)
                limits.add(doc['chunking']['recursive_threshold'])
                self.assertIsNone(record.get('source_record_issue'))
            self.assertEqual(limits,{700,1000})

    def test_web_worker_and_output_session_agree_on_threshold_filenames(self):
        from functions.web_ui.worker import execute
        from functions.experiments.cancelled_run import OutputSession
        from functions.experiments.output_ownership import output_observer
        for limit in (700,1000):
            with self.subTest(limit=limit),tempfile.TemporaryDirectory() as temp:
                settings=Settings(project_root=Path(temp))
                batch=settings.markdown_tagged_output_dir/'Financial_tagged_20261027_00-00-00'
                batch.mkdir(parents=True)
                raw='<note>\n<!-- Page: 2330_2025_P15 -->\n## 一、政策\n'+'甲'*1000+'\n'
                tagged=tag_comments(raw,None,TaggingMetadata(report_year='2025',stock_code='2330')).markdown
                source=batch/'2025_2330_tagged.md'
                source.write_text(tagged,encoding='utf-8')
                request={'stage':'chunk','ids':[source.relative_to(settings.markdown_tagged_output_dir).as_posix()],
                    'ocr':False,'chunk_mode':'parent_child','recursive_threshold':limit}
                current=request_settings(settings,request)
                session=OutputSession(current,'chunk',[source],'threshold-test')
                events=[]
                def emit(event):
                    events.append(event)
                    if 'output' in event:session.set_output_batch(event['output'])
                    if 'result' in event:session.finished()
                with output_observer(session.create):
                    execute(request,settings,emit,before_item=session.begin)
                self.assertEqual(events[-1]['state'],'completed',events)
                folder=session.batch/'parent_child'
                for name in (f'2025_2330_chunk_{limit}.json',f'2025_2330_chunk_{limit}.md',
                             f'Record/2025_2330_{limit}_reocrd'):
                    self.assertTrue((folder/name).is_file(),name)

    def test_chunk_request_validates_mode_and_three_parameters(self):
        settings = Settings()
        clean = request_settings(settings,{'stage':'chunk','ocr':False,'chunk_mode':'parent_child',
            'parent_limit':1600,'child_target':350,'recursive_threshold':750})
        self.assertEqual((clean.chunking.mode,clean.chunking.parent_limit,clean.chunking.child_target,
                          clean.chunking.recursive_threshold),('parent_child',1600,350,750))
        manual = request_settings(settings, {'stage':'chunk','ocr':True,
            'parent_limit':4000,'recursive_threshold':2000,'child_target':1200})
        self.assertEqual((manual.chunking.parent_limit, manual.chunking.recursive_threshold,
                          manual.chunking.child_target), (4000,2000,1200))
        for update in ({'chunk_mode':'other'},{'child_target':True},{'parent_limit':0},
                       {'recursive_threshold':1.5}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                request_settings(settings,{'stage':'chunk','ocr':False,**update})

    def test_mode_path_rejects_unknown_or_escaping_locations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'root'
            root.mkdir()
            for relative in ('not_batch','Financial_20261025_18-00-00/unknown',
                             'Financial_20261025_18-00-00/original/deeper'):
                path = root/relative
                path.mkdir(parents=True)
                with self.assertRaises(ValueError):
                    batch_location(path,root)


if __name__ == '__main__':
    unittest.main()
