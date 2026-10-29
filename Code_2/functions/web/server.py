"""僅本機HTTP介面：固定路由、來源檢查、工作隔離，無任意檔案存取。"""
import json
import secrets
import threading
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from Code_2.functions.web.jobs import Jobs, BusyError
from Code_2.functions.web.workspace import Workspace
from Code_2.functions.web.workspace_page import asset as workspace_asset
from Code_2.functions.web.service import metadata, history, report_path, validate_task


def make_handler(settings, web, jobs, token, workspace, guard):
    assets = Path(__file__).resolve().parent / 'static'

    def idle(server):
        if getattr(server,'closing',False):
            raise BusyError('服務正在關閉，請勿啟動新工作。')
        if (jobs.snapshot() or {}).get('status')=='running' or workspace.busy():
            raise BusyError('目前已有工作執行中，完成後才能執行問答、前處理、建庫或資料庫管理。')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # 不把問題、財報內容或檔名查詢預設寫入HTTP日誌。
            pass

        def allowed_origin(self):
            port = self.server.server_port
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            origin = self.headers.get('Origin')
            return self.headers.get('Host') in hosts and (origin is None or origin in {'http://' + h for h in hosts})

        def send_bytes(self, data, content_type, status=200, filename=None, embedded=False):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', ("default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'").replace("frame-ancestors 'none'","frame-ancestors 'self'") if embedded else "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                # 使用者關閉分頁不影響核心工作；不把中斷連線當工作成功／失敗。
                return

        def send_json(self, data, status=200):
            self.send_bytes(json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8'),
                            'application/json; charset=utf-8', status)

        def do_GET(self):
            if not self.allowed_origin():
                self.send_json({'error': '僅接受本機同來源連線。'}, 403)
                return
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            try:
                if parsed.path.startswith('/workspace/'):
                    name=parsed.path[len('/workspace/'):]
                    if name not in ('index.html','legacy.css','legacy.js','selection.js','database.js'):
                        self.send_json({'error':'找不到工作區資產。'},404)
                        return
                    values=workspace.call('bootstrap') if name in ('index.html','legacy.css','legacy.js') else {}
                    raw=workspace_asset(name,values,token).encode('utf-8')
                    mime='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript'
                    self.send_bytes(raw,mime+'; charset=utf-8',embedded=name=='index.html')
                elif parsed.path in ('/api/workspace/catalog','/api/workspace/state'):
                    self.send_json(workspace.call(parsed.path.rsplit('/',1)[-1]))
                elif parsed.path == '/':
                    html = (assets / 'index.html').read_text(encoding='utf-8').replace('__SESSION_TOKEN__', token)
                    self.send_bytes(html.encode('utf-8'), 'text/html; charset=utf-8')
                elif parsed.path in ('/api-settings.js', '/api-settings.html'):
                    path = Path(__file__).resolve().parents[3] / 'Code/functions/web_ui' / parsed.path[1:]
                    self.send_bytes(path.read_bytes(), 'text/javascript; charset=utf-8' if path.suffix=='.js' else 'text/html; charset=utf-8')
                elif parsed.path in ('/files.js', '/app.js', '/style.css', '/workspace.js', '/workspace.css', '/evaluation.js', '/saved-rerank.js'):

                    name = parsed.path[1:]
                    mime = 'text/javascript' if name.endswith('.js') else 'text/css'
                    self.send_bytes((assets / name).read_bytes(), mime + '; charset=utf-8')
                elif parsed.path.startswith('/api/files/'):
                    from Code_2.functions.web import files
                    action=parsed.path.rsplit('/',1)[-1]
                    area=params.get('area',['output'])[0];relative=params.get('path',[''])[0]
                    if action=='list':self.send_json(files.listing(settings,area,relative,int(params.get('offset',['0'])[0])))
                    elif action=='preview':self.send_json(files.preview(settings,area,relative))
                    elif action=='trash':self.send_json(files.trash_list(settings))
                    elif action=='download':
                        path=files.file_path(settings,area,relative)
                        if path.stat().st_size>web.max_report_bytes:raise ValueError('檔案超過下載上限，請從電腦開啟')
                        self.send_bytes(path.read_bytes(),'application/octet-stream',filename='file'+path.suffix.lower())
                    else:self.send_json({'error':'找不到檔案操作'},404)
                elif parsed.path == '/api/health':
                    self.send_json({'application':'financial-rag-unified','version':1})
                elif parsed.path == '/api/metadata':
                    from Code_2.config.evaluation import EvaluationSettings
                    self.send_json({**metadata(settings, web), 'evaluation_enabled': EvaluationSettings().enabled, 'evaluation_max_upload_bytes': EvaluationSettings().max_upload_bytes})
                elif parsed.path == '/api/rerank-source':
                    from Code_2.functions.experiments.saved_rerank import preview
                    self.send_json(preview(settings, params.get('run', [''])[0], params.get('candidate_unit', ['returned'])[0]))
                elif parsed.path == '/api/history':
                    self.send_json(history(settings, web))
                elif parsed.path == '/api/job':
                    job=jobs.snapshot(params.get('id',[None])[0])
                    if job and job.get('status')!='running' and params.get('after',[None])[0]==job['id']:
                        job={**job,'result':None}
                    self.send_json({'job':job,'workspace':getattr(workspace,'snapshot',lambda:workspace.call('state'))()})
                elif parsed.path in ('/api/report', '/download'):
                    name = params.get('run', [''])[0]
                    filename = 'answer.md' if parsed.path == '/api/report' else params.get('file', [''])[0]
                    path = report_path(settings, name, filename)
                    if path.stat().st_size > web.max_report_bytes:
                        raise ValueError('紀錄超過本機介面讀取上限，請從Output/Response開啟。')
                    raw = path.read_bytes()
                    if parsed.path == '/api/report':
                        self.send_json({'name': name, 'markdown': raw.decode('utf-8')})
                    else:
                        self.send_bytes(raw, 'image/svg+xml' if filename.endswith('.svg') else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if filename.endswith('.xlsx') else 'text/markdown; charset=utf-8' if filename.endswith('.md') else 'application/json; charset=utf-8', filename=filename)
                else:
                    self.send_json({'error': '找不到這個頁面。'}, 404)
            except FileNotFoundError:
                self.send_json({'error': '檔案不存在或紀錄尚未完成保存。'}, 404)
            except ValueError as error:
                self.send_json({'error': str(error)}, 400)
            except Exception as error:
                self.send_json({'error': f'本機資料讀取失敗（{type(error).__name__}），請核對操作文件。'}, 500)

        def do_POST(self):
            if not self.allowed_origin() or not secrets.compare_digest(self.headers.get('X-App-Token', ''), token):
                self.send_json({'error': '請從本機介面重新整理後操作。'}, 403)
                return
            if self.path not in ('/api/files/trash-preview','/api/files/trash','/api/files/restore','/api/tasks', '/api/api-settings', '/api/shutdown', '/api/workspace/run', '/api/workspace/cancel', '/api/workspace/database', '/api/workspace/open-output', '/api/experiments/preview'):
                self.send_json({'error': '找不到這項操作。'}, 404)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                from Code_2.config.evaluation import EvaluationSettings
                max_size = EvaluationSettings().max_upload_bytes*4//3+65536 if self.path in ('/api/experiments/preview','/api/tasks') else web.max_request_bytes
                if not 0 < size <= max_size or self.headers.get_content_type() != 'application/json':
                    raise ValueError('請求大小或格式無效')
                data = json.loads(self.rfile.read(size).decode('utf-8'))
                if not isinstance(data,dict):
                    raise ValueError('請求格式無效')
                with guard:
                    if self.path.startswith('/api/files/'):
                        from Code_2.functions.web import files
                        idle(self.server)
                        if self.path=='/api/files/trash-preview':self.send_json(files.folder_snapshot(settings,data.get('area'),data.get('path')))
                        elif self.path=='/api/files/trash':self.send_json(files.trash(settings,data))
                        else:self.send_json(files.restore(settings,data.get('id')))
                        return
                    if self.path=='/api/shutdown':
                        idle(self.server)
                        self.server.closing=True
                        self.send_json({'ok':True})
                        threading.Thread(target=self.server.shutdown,daemon=True).start()
                        return
                    if self.path=='/api/experiments/preview':
                        # EXPERIMENT_ONLY：預覽不保存工作簿、不啟動模型。
                        if not EvaluationSettings().enabled:
                            raise ValueError('Excel實驗功能已停用')
                        from Code_2.functions.experiments.eval_workbook import read_upload
                        self.send_json(read_upload(data.get('workbook_base64'),data.get('filename'),data.get('sheet')))
                        return
                    if self.path=='/api/api-settings':
                        idle(self.server)
                        from Code.functions.embedding.api_settings import manage
                        self.send_json(manage(settings.project_root,data))
                        return
                    if self.path.startswith('/api/workspace/'):
                        action=self.path.rsplit('/',1)[-1]
                        if action in ('run','database'):
                            idle(self.server)
                        self.send_json(workspace.call(action,data))
                        return
                    idle(self.server)
                    task=validate_task(data,settings)
                    self.send_json({'job':jobs.start(task)},202)
            except BusyError as error:
                self.send_json({'error': str(error)}, 409)
            except (ValueError, UnicodeError) as error:
                self.send_json({'error': str(error) if type(error) is ValueError else '請求內容格式無效'}, 400)
            except Exception as error:
                self.send_json({'error': f'無法啟動工作（{type(error).__name__}）。'}, 500)

    return Handler


def create_server(settings, web, *, jobs=None, workspace=None):
    if web.host != '127.0.0.1':
        raise ValueError('本機網頁只綁定127.0.0.1')
    jobs = jobs or Jobs(settings, web)
    workspace=workspace or Workspace(settings.project_root)
    guard=threading.RLock()
    class UnifiedServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            if sys.platform=='win32':
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
        def server_close(self):
            super().server_close()
            if jobs.thread is not None and jobs.thread.is_alive():
                jobs.thread.join()
            workspace.close()
    server = UnifiedServer((web.host, web.port), make_handler(settings, web, jobs, secrets.token_hex(32),workspace,guard))
    server.closing = False
    server.daemon_threads = True
    return server, jobs
