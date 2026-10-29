"""建庫安全停止：暫存Chroma／假向量，當前文件提交完成才停。"""
import json,tempfile,unittest,uuid
from pathlib import Path
from Code.config.embedding import Settings
from Code.functions.embedding.job_control import create_control,read_control,request_stop,remove_control,control_path
from Code.functions.embedding.direct import build_files
from Code.functions.embedding.catalog import list_indexes
from Code_2.tests.test_preparation import fixture
from Code.tests.test_vector_stage import Provider

class StopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.settings=Settings(project_root=Path(self.tmp.name))
        self.settings.fields_file.parent.mkdir(parents=True)
        self.settings.fields_file.write_bytes(Settings().fields_file.read_bytes())
        self.sources=[]
        folder=self.settings.input_dir/'Financial_chunk_20261027_01-00-00'
        folder.mkdir(parents=True)
        for year in range(2021,2026):
            p=folder/f'{year}_2330_chunk.json'
            p.write_text(json.dumps(fixture(),ensure_ascii=False).replace('2025',str(year)),encoding='utf-8')
            self.sources.append(p)
        self.ids=[p.relative_to(self.settings.input_dir).as_posix() for p in self.sources]
        self.job=uuid.uuid4().hex
        create_control(self.settings,self.job,self.ids)
    def test_stop_after_2024_never_embeds_2025(self):
        events=[];provider=Provider('bge');original=provider.embed
        def embed(texts,**kw):
            if provider.calls==0:request_stop(self.settings,self.job,self.ids[3])
            return original(texts,**kw)
        provider.embed=embed
        rows=build_files(self.sources,self.settings,backend='bge',provider_factory=lambda *a:provider,
                         progress=events.append,control_id=self.job)
        self.assertEqual(len(rows),4)
        self.assertEqual(provider.calls,4)
        self.assertTrue(all(r['status']=='indexed' for r in rows))
        self.assertEqual(events[-1]['state'],'stopped')
        self.assertEqual(events[-1]['skipped'],self.ids[4:])
        self.assertEqual(events[-1]['completed'],4)
        self.assertTrue(all('2025' not in d for i in list_indexes(self.settings) for d in i['doc_ids']))
        self.assertTrue(self.sources[4].is_file())
    def test_stop_current_finishes_commit_and_skips_next(self):
        provider=Provider('bge');original=provider.embed
        def embed(texts,**kw):
            request_stop(self.settings,self.job)
            return original(texts,**kw)
        provider.embed=embed
        rows=build_files(self.sources,self.settings,backend='bge',provider_factory=lambda *a:provider,control_id=self.job)
        self.assertEqual([r['status'] for r in rows],['indexed'])
        self.assertEqual(provider.calls,1)
        self.assertEqual(len(list_indexes(self.settings)[0]['doc_ids']),1)
    def test_stop_before_first_has_no_model_or_database(self):
        request_stop(self.settings,self.job)
        def fail(*a):raise AssertionError('不應載入模型')
        self.assertEqual(build_files(self.sources,self.settings,backend='bge',provider_factory=fail,control_id=self.job),[])
        self.assertFalse(self.settings.vector_root.exists())
    def test_control_validation_and_cleanup(self):
        with self.assertRaises(ValueError):control_path(self.settings,'../x')
        with self.assertRaises(ValueError):request_stop(self.settings,self.job,'outside')
        self.assertFalse(read_control(self.settings,self.job)['stop_requested'])
        remove_control(self.settings,self.job)
        self.assertFalse(control_path(self.settings,self.job).exists())
    def test_ui_request_does_not_kill_current_job(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from functions.web_ui.server import App
        from config.settings import Settings as PdfSettings
        app=App(PdfSettings(project_root=self.settings.project_root));app.busy=True
        app.state={'state':'running','stage':'embed','vector_job_id':self.job,'embedding_files':self.ids,
                   'completed':1,'current_id':self.ids[1]}
        from unittest.mock import Mock
        app.scope=Mock()
        app.cancel(self.ids[3])
        self.assertTrue(app.state['stop_requested'])
        self.assertEqual(read_control(self.settings,self.job)['stop_after'],self.ids[3])
        app.scope.terminate.assert_not_called()
        self.assertFalse(app.cancel_requested)
        with self.assertRaises(ValueError):app.cancel(self.ids[0])
if __name__=='__main__':unittest.main()
