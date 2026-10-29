"""統一網站至既有Code工作的薄接頭；程序環境隔離，沒有第二份處理規則。"""
import json
import os
import subprocess
import threading
from pathlib import Path
from Code.config.runtime import worker_python


class Workspace:
    def __init__(self, root):
        self.root=Path(root)
        self.lock=threading.RLock()
        self.process=None
        self.failed=False

    def call(self, action, data=None):
        with self.lock:
            if self.failed:
                raise ValueError('前處理工作區連線已中斷；請核對工作與輸出後重新啟動網站，不會自動重跑。')
            if self.process is None:
                code=self.root/'Code'
                python=worker_python(code, pdf=True)
                options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
                self.process=subprocess.Popen([str(python),'-X','utf8',str(code/'functions/web_ui/bridge.py')],
                    cwd=self.root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    text=True,encoding='utf-8',bufsize=1,**options)
            try:
                self.process.stdin.write(json.dumps({'action':action,'data':data or {}},ensure_ascii=False)+'\n')
                self.process.stdin.flush()
                line=self.process.stdout.readline()
                if not line:
                    raise OSError('pipe closed')
                result=json.loads(line)
            except (OSError,ValueError):
                self.failed=True
                raise ValueError('前處理工作區連線中斷，工作狀態未確認；不會自動重跑。') from None
            if 'error' in result:
                raise ValueError(result['error'])
            return result['result']

    def snapshot(self):
        if self.failed:
            return {'state':'unknown','busy':True,'error':'前處理管道中斷，請核對工作後重新啟動網站。'}
        return self.call('state') if self.process is not None else {'state':'idle','busy':False}

    def busy(self):
        if self.failed:
            raise ValueError('前處理工作狀態未確認，請核對後重新啟動網站。')
        return self.process is not None and self.call('state')['busy']

    def close(self):
        with self.lock:
            if self.process is not None:
                self.process.stdin.close()
                self.process.wait()
                self.process.stdout.close()
