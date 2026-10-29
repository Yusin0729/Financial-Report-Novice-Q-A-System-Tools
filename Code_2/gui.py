"""Code_2本機網頁入口；不啟動模型、API、前處理或建庫工作。"""
import argparse
import sys
import webbrowser
import json
import urllib.request
from dataclasses import replace
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Code_2.config.embedding import Settings
from Code_2.config.web import WebSettings
from Code_2.functions.web.server import create_server


def main(argv=None):
    parser = argparse.ArgumentParser(description='完整財報分析器：統一本機網站')
    parser.add_argument('--port', type=int, help='本機連接埠，預設依config/web.py')
    parser.add_argument('--open-browser', action='store_true', help='啟動後開啟瀏覽器')
    args = parser.parse_args(argv)
    web = WebSettings()
    if args.port is not None:
        if not 1 <= args.port <= 65535:
            parser.error('連接埠須為1至65535')
        web = replace(web, port=args.port)
    try:
        server, jobs = create_server(Settings(), web)
    except OSError:
        if args.open_browser:
            url=f'http://{web.host}:{web.port}'
            try:
                with urllib.request.urlopen(url+'/api/health',timeout=2) as response:
                    existing=json.load(response)
                if existing.get('application')=='financial-rag-unified':
                    webbrowser.open(url)
                    print(f'已開啟執行中的統一網站：{url}',flush=True)
                    return 0
            except (OSError,ValueError):
                pass
        print('無法啟動本機介面，連接埠可能已被使用；可用--port指定其他連接埠。')
        return 1
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'本機介面：{url}', flush=True)
    print('啟動介面不會呼叫模型API。按Ctrl+C關閉服務；執行中的工作會等待完成，不強制中止。', flush=True)
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print('\n正在關閉本機介面。', flush=True)
    finally:
        server.server_close()
        if jobs.thread is not None and jobs.thread.is_alive():
            print('等待目前工作安全完成，請勿強制關閉程序。', flush=True)
            jobs.thread.join()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
