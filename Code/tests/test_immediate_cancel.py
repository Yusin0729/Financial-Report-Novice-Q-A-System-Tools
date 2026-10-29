"""真實本次Python程序樹＋暫存輸出；不載入Docling或OCR權重。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from functions.web_ui.server import App

WORKER = r'''
import json,os,re,subprocess,sys,time
from pathlib import Path
def emit(x): print(json.dumps(x),flush=True)
def ack():
    x=json.loads(sys.stdin.readline())
    if not x['ok']:raise RuntimeError(x['error'])
    return x
request=json.loads(sys.stdin.readline())
batch=Path.cwd()/'Output/markdown_raw/Financial_20261024_00-20-00'
batch.mkdir(parents=True,exist_ok=True)
emit({'output':str(batch)})
for index,name in enumerate(request['ids']):
    emit({'current':name,'completed':index,'total':len(request['ids'])})
    emit({'item_started':index});ack()
    year,stock=re.match(r'(\d{4})Q4_(\d+)',name).groups()
    raw=batch/f'{year}_{stock}_raw.md'
    emit({'artifact_requested':str(raw)});ack()
    raw.write_bytes(b'complete' if index==0 else b'partial')
    if index==1:
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        emit({'ready_pid':child.pid})
        time.sleep(30)
    record=batch/'Record'/f'{year}_{stock}_reocrd'
    emit({'artifact_requested':str(record)});ack()
    record.write_text(json.dumps({'status':'converted_needs_review'}))
    emit({'result':{'name':name,'status':'converted_needs_review','message':'test complete'}})
    emit({'completed':index+1})
emit({'state':'completed'})
'''


def wait_for(predicate, seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.02)
    raise AssertionError('測試工作程序未在時限內到達預期狀態')


class CancelTests(unittest.TestCase):
    def test_real_process_tree_cancel_preserves_completed_and_can_restart(self):
        import psutil
        real_popen=subprocess.Popen
        with tempfile.TemporaryDirectory() as folder:
            settings=Settings(project_root=Path(folder))
            settings.source_dir.mkdir()
            names=[f'2025Q4_{stock}_Financial_Report.pdf' for stock in ('2330','2379','2317')]
            for name in names:(settings.source_dir/name).write_bytes(b'test')
            script=Path(folder)/'test_worker.py';script.write_text(WORKER,encoding='utf-8')
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            unrelated=real_popen([sys.executable,'-c','import time;time.sleep(30)'],**flags)
            app=App(settings)
            def launch(command,**kwargs):
                return real_popen([sys.executable,'-u',str(script)],**kwargs)
            try:
                with patch('functions.web_ui.server.subprocess.Popen',side_effect=launch):
                    app.start({'stage':'raw','ids':names[:2],'ocr':False})
                    wait_for(lambda:'ready_pid' in app.state or not app.busy)
                    self.assertIn('ready_pid',app.state,app.state)
                    child=psutil.Process(app.state['ready_pid'])
                    app.cancel()
                    wait_for(lambda:not app.busy)
                    self.assertEqual(app.state['state'],'cancelled',app.state)
                    wait_for(lambda:not child.is_running())
                    self.assertIsNone(unrelated.poll())
                    batch=settings.markdown_output_dir/'Financial_20261024_00-20-00'
                    self.assertEqual((batch/'2025_2330_raw.md').read_bytes(),b'complete')
                    self.assertFalse((batch/'2025_2379_raw.md').exists())
                    record=json.loads((batch/'Record/2025_2379_reocrd').read_text(encoding='utf-8'))
                    self.assertEqual(record['status'],'cancelled')
                    self.assertEqual([r['status'] for r in app.state['results']],['converted_needs_review','cancelled'])
                    app.start({'stage':'raw','ids':[names[2]],'ocr':False})
                    wait_for(lambda:not app.busy)
                    self.assertEqual(app.state['state'],'completed',app.state)
                    self.assertEqual((batch/'2025_2317_raw.md').read_bytes(),b'complete')
            finally:
                if app.busy:
                    app.cancel();wait_for(lambda:not app.busy)
                unrelated.kill();unrelated.wait()

    def test_cancel_when_idle_rejected(self):
        with self.assertRaisesRegex(ValueError,'沒有'):
            App(Settings()).cancel()


if __name__=='__main__':unittest.main()
