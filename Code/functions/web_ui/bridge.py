"""統一網站的內部JSON管道；只在PDF環境載入Code，不開第二個HTTP站。"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import SETTINGS
from config.web import POLL_INTERVAL_MS, DEFAULT_OCR_ENABLED, CHUNK_SLIDER_MAXIMA
from functions.web_ui.server import App
from functions.web_ui.catalog import STAGES, catalog

DATABASE_ACTIONS = {'indexes', 'documents', 'chunks', 'preview-delete', 'delete',
                    'preview-delete-collection', 'delete-collection'}


def dispatch(app, action, data):
    if action == 'bootstrap':
        s=app.settings
        return {'poll':POLL_INTERVAL_MS, 'ocr_checked':DEFAULT_OCR_ENABLED,
                'ocr_scale':s.ocr.scale, 'table_mode':s.table_mode,
                'chunk_mode':s.chunking.mode, 'parent_limit':s.chunking.parent_limit,
                'text_embedding_mode':s.chunking.text_embedding_mode,
                'table_embedding_mode':s.chunking.table_embedding_mode,
                'child_target':s.chunking.child_target,
                'recursive_threshold':s.chunking.recursive_threshold,
                'parent_slider_max':CHUNK_SLIDER_MAXIMA['parent_limit'],
                'threshold_slider_max':CHUNK_SLIDER_MAXIMA['recursive_threshold'],
                'child_slider_max':CHUNK_SLIDER_MAXIMA['child_target']}
    if action == 'catalog':
        return {stage:catalog(app.settings,stage) for stage in STAGES}
    if action == 'state':
        with app.lock:
            return {**app.state,'busy':app.busy}
    if action == 'run':
        app.start(data)
    elif action == 'cancel':
        app.cancel(data.get('after_file'))
    elif action == 'database':
        with app.lock:
            if app.busy or app.closing:
                raise ValueError('工作執行中，請完成後再管理資料庫')
            if data.get('action') not in DATABASE_ACTIONS:
                raise ValueError('未知資料庫操作')
            return app.vector_operation(data)
    elif action == 'open-output':
        stage=data.get('stage')
        if stage not in STAGES:
            raise ValueError('未知階段')
        target=getattr(app.settings, STAGES[stage][2])
        if not target.is_dir():
            raise ValueError('尚未產生輸出資料夾')
        os.startfile(target)
    else:
        raise ValueError('未知工作區操作')
    return {'ok':True}


def main():
    app=App(SETTINGS)
    try:
        for line in sys.stdin:
            try:
                request=json.loads(line)
                if not isinstance(request,dict) or not isinstance(request.get('data',{}),dict):
                    raise ValueError('工作區請求格式錯誤')
                result={'result':dispatch(app,request.get('action'),request.get('data',{}))}
            except ValueError as error:
                result={'error':str(error)}
            except Exception as error:
                result={'error':f'工作區操作失敗（{type(error).__name__}），請核對環境與來源。'}
            print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        # 管道關閉時等待本次核心完成，不殺死建庫或取消已完成的產物。
        while app.busy:
            time.sleep(.1)


if __name__=='__main__':
    main()
