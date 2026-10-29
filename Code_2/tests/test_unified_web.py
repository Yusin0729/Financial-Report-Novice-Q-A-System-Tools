"""統一網站的路由與互斥；僅合成工作及唯讀真實管道，不使用模型。"""
import json
import threading
import unittest
import urllib.request
import urllib.error
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from Code_2.config.embedding import Settings
from Code_2.config.web import WebSettings
from Code_2.functions.web.jobs import Jobs
from Code_2.functions.web.server import create_server
from Code_2.functions.web.workspace import Workspace
from Code_2.functions.web.workspace_page import asset


class FakeWorkspace:
    def __init__(self): self.active=False;self.calls=[];self.closed=False
    def busy(self): return self.active
    def call(self,action,data=None):
        self.calls.append((action,data))
        if action=='state':return {'busy':self.active,'state':'running' if self.active else 'idle'}
        if action=='catalog':return {'raw':[]}
        if action=='run':self.active=True
        if action=='cancel':self.active=False
        return {'ok':True}
    def close(self):self.closed=True


class UnifiedTests(unittest.TestCase):
    def test_field_selector_is_removed_from_unified_workspace(self):
        page=asset('index.html',{},'test-token')
        legacy=asset('legacy.js',{},'test-token')
        self.assertNotIn('fields.js',page)
        self.assertNotIn('embeddingFieldsButton',page+legacy)
        self.assertNotIn('embeddingFieldEntries',legacy)
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.url+'/workspace/fields.js')
        self.assertEqual(error.exception.code,404)

    def setUp(self):
        self.settings=Settings();self.web=replace(WebSettings(),port=0)
        self.workspace=FakeWorkspace();self.jobs=Jobs(self.settings,self.web)
        self.server,_=create_server(self.settings,self.web,jobs=self.jobs,workspace=self.workspace)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        html=urllib.request.urlopen(self.url).read().decode()
        self.token=html.split('name="app-token" content="')[1].split('"')[0]
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def post(self,path,body,token=True):
        headers={'Content-Type':'application/json'}
        if token:headers['X-App-Token']=self.token
        return urllib.request.urlopen(urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers=headers))
    def test_excel_preview_and_batch_validation_without_model(self):
        from Code_2.tests.test_evaluation import upload,values
        body={'workbook_base64':upload([values()]),'filename':'測試.xlsx'}
        data=json.load(self.post('/api/experiments/preview',body))
        self.assertEqual(data['valid_count'],1)
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.post('/api/experiments/preview',body,token=False)
        self.assertEqual(err.exception.code,403)
        task={**body,'action':'evaluate','ids':['1'],'backend':'bge','collection':'financial_'+'a'*24,
              'mode':'retrieve','retrieve_k':50,'evidence_k':20,'export_enabled':False}
        with patch.object(self.jobs,'start',return_value={'status':'running'}) as start:
            self.assertEqual(self.post('/api/tasks',task).status,202)
        submitted=start.call_args.args[0]
        self.assertEqual(submitted['action'],'evaluate')
        self.assertNotIn('question',submitted)
        from Code_2.config.evaluation import EvaluationSettings
        with patch('Code_2.config.evaluation.EvaluationSettings',return_value=replace(EvaluationSettings(),enabled=False)):
            with self.assertRaises(urllib.error.HTTPError):self.post('/api/experiments/preview',body)
        with urllib.request.urlopen(self.url+'/evaluation.js') as response:
            self.assertIn('EXPERIMENT_ONLY',response.read().decode())

    def test_port_is_exclusive_and_health_identifies_unified_site(self):
        with self.assertRaises(OSError):
            create_server(self.settings,replace(self.web,port=self.server.server_port))
        health=json.load(urllib.request.urlopen(self.url+'/api/health'))
        self.assertEqual(health['application'],'financial-rag-unified')

    def test_pipeline_busy_blocks_query_keys_database_and_shutdown(self):
        self.workspace.active=True
        for path,body in [('/api/tasks',{}),('/api/api-settings',{'action':'list'}),('/api/workspace/database',{'action':'delete'}),('/api/shutdown',{})]:
            with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as error:self.post(path,body)
            self.assertEqual(error.exception.code,409)
        self.assertEqual(self.workspace.calls,[])
        snapshot=json.load(urllib.request.urlopen(self.url+'/api/job'))
        self.assertTrue(snapshot['workspace']['busy'])
    def test_query_busy_blocks_pipeline_start_and_database_but_allows_state(self):
        self.jobs.current={'id':'fake','status':'running','events':[]}
        for path in ('/api/workspace/run','/api/workspace/database'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.post(path,{})
            self.assertEqual(error.exception.code,409)
        self.assertEqual(json.load(urllib.request.urlopen(self.url+'/api/workspace/state'))['state'],'idle')
    def test_run_cancel_and_token_routes(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/workspace/run',{},False)
        self.assertEqual(error.exception.code,403)
        body={'stage':'tagged','ids':['fixture'],'ocr':True}
        self.post('/api/workspace/run',body).close()
        self.assertEqual(self.workspace.calls[-1],('run',body))
        self.assertTrue(self.workspace.active)
        self.post('/api/workspace/cancel',{}).close()
        self.assertFalse(self.workspace.active)
    def test_fixed_assets_no_inline_or_arbitrary_path(self):
        config={'poll':1500,'ocr_checked':True,'ocr_scale':3,'table_mode':'accurate','chunk_mode':'original','parent_limit':1500,'recursive_threshold':700,'child_target':300,'parent_slider_max':3000,'threshold_slider_max':1500,'child_slider_max':1000}
        with patch.object(self.workspace,'call',return_value=config):
            response=urllib.request.urlopen(self.url+'/workspace/index.html')
            page=response.read().decode()
            self.assertIn("frame-ancestors 'self'",response.headers['Content-Security-Policy'])
            self.assertNotIn('<script>',page);self.assertNotIn('<style>',page)
            self.assertIn('/workspace/legacy.js',page)
            self.assertIn('/workspace.js',page)
            script=asset('legacy.js',config,'safe-token')
            self.assertIn("fetch('/api/workspace/'+path",script)
            self.assertNotIn('__TOKEN__',script)
            self.assertIn("'X-App-Token':token",script)
            self.assertNotIn("'X-UI-Token':token",script)
        for path in ('/workspace/.env','/api/workspace/unknown'):
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+path)
            self.assertEqual(error.exception.code,404)
    def test_real_pdf_environment_bridge_is_read_only_and_closes(self):
        workspace=Workspace(self.settings.project_root)
        try:
            self.assertIsNone(workspace.process)
            bootstrap=workspace.call('bootstrap')
            self.assertIn('recursive_threshold',bootstrap)
            self.assertEqual(set(workspace.call('catalog')),{'raw','processed','tagged','chunk','embed'})
            self.assertFalse(workspace.busy())
            self.assertEqual(workspace.call('state')['results'],[])
        finally:workspace.close()
        self.assertEqual(workspace.process.returncode,0)


if __name__=='__main__':unittest.main()
