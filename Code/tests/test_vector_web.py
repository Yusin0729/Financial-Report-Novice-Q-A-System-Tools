"""第五階段HTTP與程序邊界；全部使用模擬工作，不執行模型。"""
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from functions.web_ui.server import App, make_server
from functions.web_ui.catalog import catalog, selected_paths


class VectorWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(project_root=Path(self.tmp.name))
        root = self.settings.markdown_chunk_output_dir / 'Financial_chunk_20261025_12-00-00'
        for mode in ('original', 'parent_child'):
            path = root / mode / '2025_2330_chunk.json'
            path.parent.mkdir(parents=True)
            path.write_text('{}',encoding='utf-8')

    def test_selection_keeps_modes_and_no_output_session(self):
        rows = catalog(self.settings,'embed')
        self.assertEqual(len(rows),2)
        self.assertEqual(len(selected_paths(self.settings,'embed',[r['id'] for r in rows])),2)
        app = App(self.settings)
        with patch.object(app, 'run_embedding') as run, patch('functions.experiments.cancelled_run.OutputSession') as output:
            app.run({'stage':'embed'})
            run.assert_called_once()
            output.assert_not_called()
        app.busy=True
        app.state={'stage':'embed','state':'running'}
        with self.assertRaisesRegex(ValueError,'舊版啟動'): app.cancel()

    def test_stream_uses_embedding_environment(self):
        app=App(self.settings)
        app.state={'stage':'embed','state':'running','results':[]}
        class Process:
            def __init__(self,*args,**kwargs):
                self.stdin=io.StringIO()
                self.stdout=io.StringIO(json.dumps({'result':{'status':'indexed'},'completed':1})+'\n'+json.dumps({'state':'completed'})+'\n')
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def wait(self): return 0
        with patch('functions.web_ui.server.subprocess.Popen',side_effect=Process) as popen:
            app.run_embedding({'stage':'embed','backend':'bge','ids':['test']})
        self.assertIn('.venv',popen.call_args.args[0][0])
        self.assertNotIn('.venv_pdf',popen.call_args.args[0][0])
        self.assertEqual(app.state['state'],'completed')
        self.assertEqual(len(app.state['results']),1)

    def test_safe_stop_route_keeps_current_document_running(self):
        from functions.embedding.job_control import create_control,read_control,remove_control
        import uuid
        ids=[r['id'] for r in catalog(self.settings,'embed')]
        job=uuid.uuid4().hex
        create_control(self.settings,job,ids)
        self.addCleanup(remove_control,self.settings,job)
        server=make_server(self.settings)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        app=server.app;app.busy=True
        app.state={'state':'running','stage':'embed','completed':0,'results':[],
                   'vector_job_id':job,'embedding_files':ids}
        body=json.dumps({'after_file':ids[0]}).encode()
        request=Request(f'http://127.0.0.1:{server.server_port}/api/cancel',data=body,
                        headers={'X-UI-Token':app.token,'Content-Type':'application/json'})
        with urlopen(request) as response:self.assertEqual(response.status,200)
        self.assertTrue(app.busy)
        self.assertEqual(app.state['state'],'running')
        self.assertEqual(read_control(self.settings,job)['stop_after'],ids[0])
        app.busy=False

    def test_api_settings_route_uses_separate_rpc_without_job_or_secret_state(self):
        server=make_server(self.settings)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        headers={'X-UI-Token':server.app.token,'Content-Type':'application/json'}
        for asset in ('/api-settings.js','/api-settings.html'):
            self.assertEqual(urlopen(base+asset).status,200)
        body=b'{"action":"add","api_key":"FAKE-KEY-ONLY"}'
        with patch.object(server.app,'vector_operation',return_value={'profiles':[]}) as operation:
            data=json.load(urlopen(Request(base+'/api/api-settings',data=body,headers=headers)))
            self.assertEqual(data,{'profiles':[]})
            self.assertEqual(operation.call_args.args[0]['action'],'api-settings')
            self.assertNotIn('FAKE-KEY',json.dumps(server.app.state))
        with self.assertRaises(HTTPError): urlopen(Request(base+'/api/api-settings',data=body))

    def test_collection_removal_routes_still_require_token_and_idle(self):
        server=make_server(self.settings)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        headers={'X-UI-Token':server.app.token,'Content-Type':'application/json'}
        for action in ('preview-delete-collection','delete-collection'):
            body=json.dumps({'action':action,'backend':'bge','collection':'test-only'}).encode()
            with self.assertRaises(HTTPError): urlopen(Request(base+'/api/database',data=body))
            with patch.object(server.app,'vector_operation',return_value={'test_only':True}) as operation:
                self.assertTrue(json.load(urlopen(Request(base+'/api/database',data=body,headers=headers)))['test_only'])
                self.assertEqual(operation.call_args.args[0]['action'],action)
                server.app.busy=True
                with self.assertRaises(HTTPError): urlopen(Request(base+'/api/database',data=body,headers=headers))
                self.assertEqual(operation.call_count,1)
                server.app.busy=False

    def test_http_management_token_busy_and_fifth_stage(self):
        server=make_server(self.settings)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        headers={'X-UI-Token':server.app.token,'Content-Type':'application/json'}
        page=urlopen(base).read().decode('utf-8')
        self.assertIn('data-stage="embed"',page)
        self.assertIn('dbDelete',page)
        body=b'{"action":"indexes"}'
        with self.assertRaises(HTTPError): urlopen(Request(base+'/api/database',data=body))
        with patch.object(server.app,'vector_operation',return_value={'indexes':[]}) as operation:
            result=json.load(urlopen(Request(base+'/api/database',data=body,headers=headers)))
            self.assertEqual(result,{'indexes':[]})
            operation.assert_called_once()
            server.app.busy=True
            with self.assertRaises(HTTPError): urlopen(Request(base+'/api/database',data=body,headers=headers))
            self.assertEqual(operation.call_count,1)
            server.app.busy=False


if __name__ == '__main__': unittest.main()
