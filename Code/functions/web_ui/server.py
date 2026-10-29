"""標準庫本機 HTTP 服務；單一工作、來源白名單、隨機權杖。"""
import json
import os
import secrets
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from config.web import HOST, PORT, MAX_REQUEST_BYTES, POLL_INTERVAL_MS, DEFAULT_OCR_ENABLED, CHUNK_SLIDER_MAXIMA
from functions.web_ui.catalog import STAGES, catalog, selected_paths
from functions.web_ui.request_settings import request_settings
from functions.web_ui.process_scope import ProcessScope
from config.runtime import PDF_ENVIRONMENT_NAME, worker_python

class App:
    def __init__(self, settings):
        self.settings = settings
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.state = {'state': 'idle', 'results': [], 'completed': 0, 'total': 0}
        self.busy = False
        self.closing = False
        self.cancel_requested = False
        self.scope = None
        self.pipeline_active = False

    def start(self, request):
        with self.lock:
            if self.busy or self.closing:
                raise ValueError('已有工作執行中或服務正在關閉')
            from functions.web_ui.pipeline import validate_request
            stages = validate_request(self.settings, request)
            stage = request.get('stage')
            selected_paths(self.settings, stage, request.get('ids'))
            request_settings(self.settings, request)
            if stage == 'embed':
                if request.get('backend') not in ('bge', 'voyage'):
                    raise ValueError('請選BGE或Voyage模型')
                if any(type(request.get(k, False)) is not bool for k in ('check_only', 'allow_voyage_api')):
                    raise ValueError('建庫設定格式無效')
                if request['backend'] == 'voyage' and not request.get('allow_voyage_api'):
                    raise ValueError('請先明確啟用Voyage API')
            if stage == 'embed':
                from functions.embedding.index_target import validate_choice
                validate_choice(request.get('index_mode'), request.get('index_name'), request.get('collection'))
                from functions.embedding.job_control import create_control
                request=dict(request)
                request['vector_job_id']=uuid.uuid4().hex
                create_control(self.settings,request['vector_job_id'],request['ids'])
            self.state = {'state': 'running', 'stage': stage, 'results': [], 'completed': 0,
                          'total': len(request['ids']), 'current': '準備工作環境'}
            if stage == 'embed':
                self.state.update(vector_job_id=request['vector_job_id'],embedding_files=list(request['ids']),stop_requested=False)
            self.busy = True
            self.pipeline_active = len(stages) > 1
            self.cancel_requested = False
            threading.Thread(target=self.run, args=(request,), daemon=True).start()

    def cancel(self, after_file=None):
        with self.lock:
            if not self.busy or (self.state['state'] not in ('running', 'cancelling') and not self.pipeline_active):
                raise ValueError('目前沒有可以取消的工作')
            if self.state.get('stage') == 'embed':
                job_id=self.state.get('vector_job_id')
                if not job_id:
                    raise ValueError('本批工作由舊版啟動，需等目前工作完成；未強制中斷索引')
                files=self.state['embedding_files']
                if after_file is not None and after_file not in files[self.state.get('completed',0):]:
                    raise ValueError('請選擇目前或尚未開始的文件作為停止位置')
                from functions.embedding.job_control import request_stop
                request_stop(self.settings,job_id,after_file)
                self.state.update(stop_requested=True,stop_after=after_file)
                return
            if self.cancel_requested:
                return
            self.cancel_requested = True
            self.state.update(state='cancelling', current='立即停止本次工作程序，清理未完成輸出')
            if self.scope is not None:
                try:
                    self.scope.terminate()
                except OSError:
                    self.cancel_requested = False
                    self.state.update(state='running', error='無法停止本次程序；未宣稱取消成功')
                    raise ValueError('無法停止本次工作程序') from None

    def run(self, request):
        if not self.pipeline_active:
            return self.run_single(request)
        try:
            from functions.web_ui.pipeline import run_pipeline
            run_pipeline(self, request)
        finally:
            with self.lock:
                self.pipeline_active = False
                self.busy = False

    def run_single(self, request):
        process = None
        scope = None
        session = None
        try:
            if request['stage'] == 'embed':
                self.run_embedding(request)
                return
            from functions.experiments.cancelled_run import OutputSession
            # EXPERIMENT_ONLY：取消只清理此工作建立的檢查產物，不讀Record傳遞正文。
            session = OutputSession(request_settings(self.settings, request), request['stage'],
                                    selected_paths(self.settings, request['stage'], request['ids']), uuid.uuid4().hex)
            code = self.settings.project_root / 'Code'
            python = worker_python(code, pdf=True)
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session':True}
            process = subprocess.Popen([str(python), '-X', 'utf8', str(code / 'functions/web_ui/worker.py')],
                cwd=self.settings.project_root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                **options)
            # worker先等stdin，不會在納入本次程序範圍前載入模型或啟動子程序。
            scope = ProcessScope(process)
            with self.lock:
                self.scope = scope
                if self.cancel_requested:
                    scope.terminate()
                else:
                    process.stdin.write(json.dumps(request, ensure_ascii=False)+'\n')
                    process.stdin.flush()
            for line in process.stdout:
                event = json.loads(line)
                with self.lock:
                    if 'output' in event:
                        session.set_output_batch(event['output'])
                    if 'item_started' in event or 'artifact_requested' in event:
                        if self.cancel_requested:
                            continue
                        try:
                            if 'item_started' in event:
                                session.begin(event['item_started'])
                                reply = {'ok':True}
                            else:
                                reply = {'ok':True, 'identity':session.create(event['artifact_requested'])}
                        except (OSError, ValueError) as error:
                            reply = {'ok':False, 'error':str(error)}
                        process.stdin.write(json.dumps(reply, ensure_ascii=False)+'\n')
                        process.stdin.flush()
                        continue
                    if 'result' in event:
                        self.state['results'].append({**event.pop('result'), 'stage':request['stage']})
                        session.finished()
                    if not self.cancel_requested:
                        self.state.update(event)
            code = process.wait()
            with self.lock:
                if not self.cancel_requested and (code != 0 or self.state['state'] == 'running'):
                    self.state.update(state='failed', error='工作程序未正常完成，不能視為成功；請查看批次 Record')
        except Exception:
            with self.lock:
                if not self.cancel_requested:
                    self.state.update(state='failed', error='無法完成工作，請確認 Code/.venv_pdf、來源及程序隔離權限')
        finally:
            if scope is not None:
                scope.close()  # Windows只關閉本次Job，絕不依程序名稱終止。
            elif process is not None and process.poll() is None:
                process.kill()  # 尚未收到stdin，未進入模型／子程序階段。
            if process is not None:
                process.wait()
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()
            with self.lock:
                if session is not None and (self.cancel_requested or self.state['state'] == 'failed'):
                    result, issues = session.cancel(**({} if self.cancel_requested else
                        {'reason':'工作程序異常停止', 'status':'failed'}))
                    if result:
                        self.state['results'].append(result)
                    if self.cancel_requested:
                        self.state.update(state='cancelled_with_cleanup_errors' if issues else 'cancelled',
                                          current='本次工作已停止，後續檔案未執行')
                    if issues:
                        self.state['error'] = '；'.join(issues)
                elif self.cancel_requested:
                    self.state.update(state='cancelled', current='已取消，尚未開始處理檔案')
                if request.get('vector_job_id'):
                    from functions.embedding.job_control import remove_control
                    try:
                        remove_control(self.settings,request['vector_job_id'])
                    except OSError:
                        self.state['error']='本批已結束，但工作控制檔清理失敗，請核對.runtime/vector_jobs'
                self.scope = None
                if not self.pipeline_active:
                    self.busy = False

    def vector_operation(self, request):
        """獨立環境操作向量庫；不在PDF環境匯入Chroma或同名functions。"""
        code = self.settings.project_root / 'Code'
        python = worker_python(code)
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        process = subprocess.run([str(python), '-X', 'utf8', str(code / 'vector.py'), '--rpc'],
            input=json.dumps(request, ensure_ascii=False)+'\n', cwd=self.settings.project_root,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', **options)
        events = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
        result = events[-1] if events else {'error': '向量庫程序未回傳結果'}
        if result.get('error') or process.returncode:
            raise ValueError(result.get('error', '向量庫操作失敗'))
        return result

    def run_embedding(self, request):
        code = self.settings.project_root / 'Code'
        python = worker_python(code)
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        with subprocess.Popen([str(python), '-X', 'utf8', str(code / 'vector.py'), '--rpc'],
                cwd=self.settings.project_root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding='utf-8', **options) as process:
            payload = {**request, 'action': 'build'}
            process.stdin.write(json.dumps(payload, ensure_ascii=False)+'\n')
            process.stdin.flush()
            process.stdin.close()
            for line in process.stdout:
                event = json.loads(line)
                with self.lock:
                    if 'result' in event:
                        self.state['results'].append({**event.pop('result'), 'stage':request['stage']})
                    self.state.update(event)
            if process.wait() and self.state.get('state') not in ('completed_with_errors', 'failed'):
                self.state.update(state='failed', error='建庫程序異常停止，未確認提交的文件不得視為成功')
            if self.state.get('state') == 'running':
                self.state.update(state='failed', error='建庫程序缺少完成事件')


def make_server(settings):
    app = App(settings)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, value, content_type='application/json; charset=utf-8'):
            data = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def valid(self):
            host = f'{HOST}:{self.server.server_port}'
            origin = self.headers.get('Origin')
            return self.headers.get('Host') == host and (not origin or origin == f'http://{host}')

        def do_GET(self):
            if not self.valid():
                return self.reply(403, {'error': '僅允許本機介面'})
            if self.path == '/':
                page = Path(__file__).with_name('index.html').read_text(encoding='utf-8')
                return self.reply(200, page.replace('__TOKEN__', app.token).replace('__POLL__', str(POLL_INTERVAL_MS))
                    .replace('__OCR_SCALE__', str(settings.ocr.scale)).replace('__TABLE_MODE__', settings.table_mode)
                    .replace('__CHUNK_MODE__', settings.chunking.mode)
                    .replace('__TEXT_EMBEDDING_MODE__', settings.chunking.text_embedding_mode)
                    .replace('__TABLE_EMBEDDING_MODE__', settings.chunking.table_embedding_mode)
                    .replace('__PARENT_LIMIT__', str(settings.chunking.parent_limit))
                    .replace('__CHILD_TARGET__', str(settings.chunking.child_target))
                    .replace('__RECURSIVE_THRESHOLD__', str(settings.chunking.recursive_threshold))
                    .replace('__OCR_CHECKED__', 'checked' if DEFAULT_OCR_ENABLED else '')
                    .replace('__PARENT_SLIDER_MAX__', str(CHUNK_SLIDER_MAXIMA['parent_limit']))
                    .replace('__THRESHOLD_SLIDER_MAX__', str(CHUNK_SLIDER_MAXIMA['recursive_threshold']))
                    .replace('__CHILD_SLIDER_MAX__', str(CHUNK_SLIDER_MAXIMA['child_target'])), 'text/html; charset=utf-8')
            if self.path in ('/api-settings.js', '/api-settings.html'):
                name = self.path[1:]
                return self.reply(200, Path(__file__).with_name(name).read_text(encoding='utf-8'),
                    'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/html; charset=utf-8')
            if self.path == '/database.js':
                return self.reply(200, Path(__file__).with_name('database.js').read_text(encoding='utf-8'), 'text/javascript; charset=utf-8')
            if self.path == '/selection.js':
                return self.reply(200, Path(__file__).with_name('selection.js').read_text(encoding='utf-8'),
                                  'text/javascript; charset=utf-8')
            if self.headers.get('X-UI-Token') != app.token:
                return self.reply(403, {'error': '請重新開啟介面'})
            if self.path == '/api/catalog':
                return self.reply(200, {stage: catalog(settings, stage) for stage in STAGES})
            if self.path == '/api/state':
                with app.lock:
                    return self.reply(200, {**app.state, 'busy': app.busy})
            return self.reply(404, {'error': '找不到頁面'})

        def do_POST(self):
            if not self.valid() or self.headers.get('X-UI-Token') != app.token:
                return self.reply(403, {'error': '請從本機介面操作'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise ValueError('請求大小錯誤')
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError('請求格式錯誤')
                if self.path == '/api/run':
                    app.start(request)
                elif self.path == '/api/api-settings':
                    with app.lock:
                        if app.busy or app.closing: raise ValueError('請等目前工作結束再修改API設定')
                        result = app.vector_operation({'action':'api-settings', 'request':request})
                    return self.reply(200, result)
                elif self.path == '/api/database':
                    with app.lock:
                        if app.busy or app.closing:
                            raise ValueError('工作執行中，請完成後再管理資料庫')
                        if request.get('action') not in ('indexes', 'documents', 'chunks', 'preview-delete', 'delete', 'preview-delete-collection', 'delete-collection'):
                            raise ValueError('未知資料庫操作')
                        result = app.vector_operation(request)
                    return self.reply(200, result)
                elif self.path == '/api/cancel':
                    app.cancel(request.get('after_file'))
                elif self.path == '/api/open-output':
                    stage = request.get('stage')
                    if stage not in STAGES:
                        raise ValueError('未知階段')
                    target = getattr(settings, STAGES[stage][2])
                    if not target.is_dir():
                        raise ValueError('尚未產生輸出資料夾')
                    os.startfile(target)
                elif self.path == '/api/shutdown':
                    with app.lock:
                        if app.busy:
                            raise ValueError('正在處理，請等工作結束再關閉服務')
                        app.closing = True
                    self.reply(200, {'ok': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                else:
                    return self.reply(404, {'error': '未知操作'})
                self.reply(200, {'ok': True})
            except (ValueError, KeyError, TypeError) as error:
                self.reply(400, {'error': str(error)})
            except Exception:
                self.reply(500, {'error': '操作未完成，請確認本機環境'})
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.app = app
    return server
