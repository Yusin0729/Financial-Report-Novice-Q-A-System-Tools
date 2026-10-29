"""同時一項工作；子程序隔離stdout／模型，最近工作只保存在記憶體。"""
import json
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone


class BusyError(ValueError):
    pass


class Jobs:
    def __init__(self, settings, web, *, popen=subprocess.Popen):
        self.settings, self.web, self.popen = settings, web, popen
        self.lock = threading.Lock()
        self.current = None
        self.thread = None

    def start(self, task):
        with self.lock:
            if self.current and self.current['status'] == 'running':
                raise BusyError('目前已有工作執行中，完成後才能啟動下一項。')
            job = {'id': uuid.uuid4().hex, 'action': task['action'], 'status': 'running',
                   'created_at': datetime.now(timezone.utc).isoformat(), 'events': [], 'result': None}
            self.current = job
            self.thread = threading.Thread(target=self._run, args=(job, task), daemon=False)
            self.thread.start()
            return dict(job)

    def _run(self, job, task):
        started = time.monotonic()
        process = None
        terminal = None
        try:
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
            process = self.popen([sys.executable, '-X', 'utf8', '-m', 'Code_2.functions.web.worker'],
                                 cwd=str(self.settings.project_root), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, encoding='utf-8', bufsize=1, **options)
            process.stdin.write(json.dumps(task, ensure_ascii=False) + '\n')
            process.stdin.close()
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if event.get('type') == 'progress' and isinstance(event.get('message'), str):
                    with self.lock:
                        job['events'].append(event['message'])
                        del job['events'][:-self.web.max_job_events]
                elif event.get('type') in ('result', 'failure'):
                    terminal = event
            code = process.wait()
            with self.lock:
                if code == 0 and terminal and terminal['type'] == 'result':
                    job.update(status=terminal['outcome'], result=terminal['result'])
                else:
                    job.update(status='failed', error=(terminal['message'] if terminal and terminal['type'] == 'failure'
                                                       else '工作程序已停止，未取得有效結果；未自動重試。'))
        except Exception as error:
            with self.lock:
                job.update(status='failed', error=f'無法完成工作（{type(error).__name__}）；未重試。')
        finally:
            if process is not None:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                process.stdout.close()
                process.wait()
            with self.lock:
                job['elapsed_seconds'] = round(time.monotonic() - started, 2)

    def snapshot(self, job_id=None):
        with self.lock:
            if self.current is None or (job_id is not None and self.current['id'] != job_id):
                return None
            # 僅複製可變事件清單；結果完成後不再修改。
            return {**self.current, 'events': list(self.current['events'])}
