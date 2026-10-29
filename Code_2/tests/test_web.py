"""本機HTTP與模擬工作測試：不讀金鑰、不啟動模型、不呼叫外部服務。"""
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from Code_2.config.embedding import Settings
from Code_2.config.web import WebSettings
from Code_2.functions.web import service, worker
from Code_2.functions.web.jobs import Jobs, BusyError
from Code_2.functions.web.server import create_server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = replace(Settings(), project_root=Path(self.temp.name))
        self.settings.fields_file.parent.mkdir(parents=True)
        self.settings.fields_file.write_bytes(Settings().fields_file.read_bytes())
        self.web = replace(WebSettings(), port=0)
        self.query = dict(action='query', question='有何依據？', backend='bge',
                          collection='financial_' + 'a'*24, mode='answer',
                          retrieve_k=50, evidence_k=10, stock_code='0050', report_year=2025,
                          export_enabled=False)

    def tearDown(self):
        self.temp.cleanup()

    def test_query_contract(self):
        clean = service.validate_task(self.query, self.settings)
        self.assertEqual(clean['stock_code'], '0050')
        self.assertFalse(clean['export_enabled'])

    def test_reject_invalid_counts_and_unknown_parameters(self):
        for changes in ({'retrieve_k':True}, {'evidence_k':51}, {'mode':'rewrite'},
                        {'report_year':'2025'}, {'collection':'../../.env'}, {'key':'secret'}, {'mode':[]}, {'action':[]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                service.validate_task({**self.query, **changes}, self.settings)

    def test_retrieve_does_not_constrain_unused_rerank(self):
        self.assertEqual(service.validate_task({**self.query, 'mode':'retrieve', 'retrieve_k':3}, self.settings)['retrieve_k'],3)

    def test_build_actions_moved_to_code(self):
        for action in ('prepare', 'embed'):
            with self.assertRaisesRegex(ValueError, '第五階段'):
                service.validate_task({'action':action}, self.settings)
            with self.assertRaisesRegex(ValueError, '第五階段'):
                service.execute_task({'action':action}, self.settings)

    def test_report_read_and_traversal(self):
        name='qa_20261022_12-30-00_123456'
        folder=self.settings.response_dir/name
        folder.mkdir(parents=True)
        (folder/'answer.md').write_text('# 真實原文\n<table>',encoding='utf-8')
        self.assertEqual(service.reports(self.settings,self.web)[0]['name'],name)
        for run,file in ((name,'.env'),('../.env','answer.md'),(name,'../result.json')):
            with self.assertRaises(ValueError):service.report_path(self.settings,run,file)

    def test_dispatch_query_preserves_mode_and_counts(self):
        task=service.validate_task({**self.query,'mode':'rerank','retrieve_k':7,'evidence_k':3,
                                    'include_heading_parent':True},self.settings)
        with patch('Code_2.functions.qa.run.run_question',return_value={'status':'reranked'}) as run:
            self.assertEqual(service.execute_task(task,self.settings)['query']['status'],'reranked')
        self.assertEqual(run.call_args.kwargs['mode'],'rerank')
        self.assertEqual(run.call_args.kwargs['qa'].evidence_k,3)
        self.assertTrue(run.call_args.kwargs['qa'].include_heading_parent)
        self.assertFalse(run.call_args.args[1].export_enabled)

    def test_api_settings_http_add_and_delete_without_secret_echo(self):
        server,jobs=create_server(self.settings,self.web)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            page=urllib.request.urlopen(base).read().decode('utf-8')
            token=page.split('name="app-token" content="')[1].split('"')[0]
            for asset in ('/api-settings.js','/api-settings.html'):
                self.assertEqual(urllib.request.urlopen(base+asset).status,200)
            request={'action':'add','name':'假金鑰測試','purpose':'answer','provider':'openai','model':'gpt-test-only','api_key':'FAKE-HTTP-SECRET-ONLY'}
            raw=json.dumps(request).encode()
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(base+'/api/api-settings',data=raw))
            headers={'Content-Type':'application/json','X-App-Token':token}
            result=urllib.request.urlopen(urllib.request.Request(base+'/api/api-settings',data=raw,headers=headers)).read().decode()
            self.assertNotIn('FAKE-HTTP-SECRET-ONLY',result)
            data=json.loads(result);identity=data['credentials'][0]['id']
            self.assertEqual(data['profiles'][0]['provider'],'openai')
            raw=json.dumps({'action':'delete-key','id':identity}).encode()
            data=json.load(urllib.request.urlopen(urllib.request.Request(base+'/api/api-settings',data=raw,headers=headers)))
            self.assertEqual(data['profiles'],[])
            self.assertNotIn('FAKE-HTTP-SECRET-ONLY',(self.settings.project_root/'.env').read_text())
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_outcome_never_masks_partial_failure(self):
        self.assertEqual(service.task_outcome({'action':'embed','rows':[{'status':'failed'}]}),'needs_attention')
        self.assertEqual(service.task_outcome({'action':'query','query':{'status':'answered','export_status':'failed'}}),'failed')

    def test_progress_drops_raw_logs(self):
        with patch.object(worker,'emit') as emit:
            stream=worker.Progress()
            stream.write('secret=do-not-forward\n向量化 2025_2330：1–2/3\n')
        self.assertEqual(emit.call_count,1)
        self.assertNotIn('secret',str(emit.call_args))

    def test_worker_failure_does_not_leak_exception_body(self):
        with patch.object(worker.sys,'stdin',io.StringIO(json.dumps(self.query))), patch.object(worker,'execute_task',side_effect=RuntimeError('secret-body')), patch.object(worker,'emit') as emit:
            self.assertEqual(worker.main(),1)
        self.assertNotIn('secret-body',str(emit.call_args_list))
        self.assertEqual(emit.call_args.args[0]['type'],'failure')

    def test_real_worker_protocol_rejects_invalid_task_before_model(self):
        process = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'Code_2.functions.web.worker'],
                                 input='{"action":"invalid"}', text=True, encoding='utf-8',
                                 capture_output=True, cwd=Settings().project_root, timeout=15)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(json.loads(process.stdout)['type'], 'failure')
        self.assertNotIn('Traceback', process.stdout)

    def test_single_job_and_simulated_subprocess(self):
        started,finish=threading.Event(),threading.Event()
        class Process:
            def __init__(self,*args,**kwargs):
                self.stdin=io.StringIO()
                self.stdout=io.StringIO(json.dumps({'type':'result','outcome':'completed','result':{'action':'query','query':{'status':'retrieved'}}})+'\n')
                started.set();finish.wait(3)
            def wait(self):return 0
        jobs=Jobs(self.settings,self.web,popen=Process)
        first=jobs.start(self.query)
        try:
            self.assertTrue(started.wait(2))
            with self.assertRaises(BusyError):jobs.start(self.query)
            self.assertIsNone(jobs.snapshot('not-this-job'))
        finally:
            finish.set();jobs.thread.join(3)
        self.assertEqual(jobs.snapshot(first['id'])['status'],'completed')

    def test_http_routes_token_origin_and_safe_assets(self):
        jobs=Jobs(self.settings,self.web,popen=lambda *a,**k:None)
        server,_=create_server(self.settings,self.web,jobs=jobs)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        def request(path,body=None,headers=None):
            return urllib.request.urlopen(urllib.request.Request(url+path,data=body,headers=headers or {}))
        try:
            with request('/') as response:
                html=response.read().decode('utf-8')
                token=html.split('name="app-token" content="')[1].split('"')[0]
                self.assertIn('查詢與問答',html)
                self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            for path in ('/app.js','/style.css'):
                with request(path) as response:self.assertEqual(response.status,200)
            for path in ('/.env','/../../.env'):
                with self.assertRaises(urllib.error.HTTPError) as error:request(path)
                self.assertEqual(error.exception.code,404)
            body=json.dumps(self.query).encode()
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/tasks',body,{'Content-Type':'application/json'})
            self.assertEqual(error.exception.code,403)
            headers={'Content-Type':'application/json','X-App-Token':token,'Origin':'https://external.invalid'}
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/tasks',body,headers)
            self.assertEqual(error.exception.code,403)
            headers.pop('Origin')
            with patch.object(jobs,'start',return_value={'id':'mock','status':'running'}) as start:
                with request('/api/tasks',body,headers) as response:self.assertEqual(response.status,202)
                self.assertEqual(start.call_args.args[0]['mode'],'answer')
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
