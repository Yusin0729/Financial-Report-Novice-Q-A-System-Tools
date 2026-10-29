"""第五階段獨立入口；沿用Code/.venv，不把PDF環境與問答模組混入建庫。"""
import argparse
import contextlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from Code.config.embedding import Settings
from Code.functions.embedding.direct import build_files


def dispatch(request, settings, emit):
    action = request.get('action')
    if action == 'api-settings':
        from Code.functions.embedding.api_settings import manage
        return manage(settings.project_root, request.get('request', {}))
    if action == 'indexes':
        from Code.functions.embedding.catalog import list_indexes
        return {'indexes': list_indexes(settings)}
    if action == 'build':
        ids = request.get('ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
            raise ValueError('請選chunk JSON')
        paths = []
        root = settings.input_dir.resolve()
        for identity in ids:
            path = root / identity
            if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
                raise ValueError('來源超出chunk目錄或不存在')
            paths.append(path)
        allow = request.get('allow_voyage_api', False)
        if type(allow) is not bool:
            raise ValueError('API啟用設定無效')
        profile_id = request.get('embedding_profile')
        if profile_id is not None and (not isinstance(profile_id, str) or not profile_id):
            raise ValueError('Embedding設定ID無效')
        if profile_id:
            from Code.functions.embedding.api_settings import resolve_profile
            profile, _ = resolve_profile(settings.project_root, profile_id, 'embedding')
            if request.get('backend') != 'voyage': raise ValueError('API設定與embedding模型不符')
        from Code.functions.embedding.index_target import resolve_target
        batch_prefix = request.get('index_name') if request.get('index_mode')=='batch' else None
        if request.get('index_mode')=='batch':
            from Code.functions.embedding.index_target import validate_choice
            validate_choice('batch', batch_prefix, request.get('collection'))
        target = None if request.get('index_mode')=='batch' else resolve_target(settings, request.get('backend'), mode=request.get('index_mode'),
            name=request.get('index_name'), collection=request.get('collection'))
        if 'text_embedding_mode' in request or 'table_embedding_mode' in request:
            raise ValueError('Embedding脈絡請在第四階段設定，建庫沿用chunk設定')
        current = replace(settings, allow_voyage_api=allow, embedding_profile=profile_id)
        terminal={}
        def progress(event):
            if event.get('state')=='stopped':terminal.update(event)
            emit(event)
        rows = build_files(paths, current, backend=request.get('backend'),
                           check_only=request.get('check_only', False), progress=progress,
                           control_id=request.get('vector_job_id'), index_target=target, batch_prefix=batch_prefix)
        return terminal or {'state': 'completed_with_errors' if any(r['status'] not in ('indexed', 'checked', 'already_indexed') for r in rows) else 'completed'}
    if action in ('preview-delete-collection', 'delete-collection'):
        from Code.functions.embedding.collection_management import collection_snapshot, delete_collection
        if action == 'preview-delete-collection':
            return collection_snapshot(settings, request.get('backend'), request.get('collection'))
        return delete_collection(settings, request.get('backend'), request.get('collection'), request.get('token'))
    from Code.functions.embedding.management import open_index, documents, snapshot, delete_documents, browse_chunks
    store = open_index(settings, request.get('backend'), request.get('collection'))
    try:
        if action == 'documents':
            return {'documents': documents(store, doc_id=request.get('doc_id', ''),
                stock_code=request.get('stock_code', ''), year=request.get('year'))}
        if action == 'chunks':
            return browse_chunks(store, request.get('doc_id'), request.get('offset', 0))
        if action == 'preview-delete':
            return snapshot(store, request.get('doc_ids'))
        if action == 'delete':
            return delete_documents(store, request.get('doc_ids'), request.get('token'))
        raise ValueError('未知資料庫操作')
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description='第五階段：chunk JSON直接建立向量庫')
    parser.add_argument('--rpc', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--source', action='append', help='相對於Output/markdown_chunk的JSON路徑，可重複指定')
    parser.add_argument('--backend', choices=('bge', 'voyage'), default='bge')
    target_group=parser.add_mutually_exclusive_group()
    target_group.add_argument('--index-name', help='新建獨立實驗索引的顯示名稱')
    target_group.add_argument('--collection', help='加入指定既有索引集合')
    target_group.add_argument('--batch-index-prefix', help='依切法及脈絡分組，批次建立獨立索引')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--allow-voyage-api', action='store_true')
    args = parser.parse_args()
    request = json.loads(sys.stdin.readline()) if args.rpc else {
        'action': 'build', 'ids': args.source, 'backend': args.backend,
        'check_only': args.check_only, 'allow_voyage_api': args.allow_voyage_api,
        'index_mode':'batch' if args.batch_index_prefix else 'new' if args.index_name else 'existing' if args.collection else None,
        'index_name':args.batch_index_prefix or args.index_name, 'collection':args.collection}
    output = sys.stdout
    def emit(value):
        output.write(json.dumps(value, ensure_ascii=False) + '\n')
        output.flush()
    try:
        with open(os.devnull, 'w', encoding='utf-8') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = dispatch(request, Settings(), emit)
        emit(result)
        return int(result.get('state') == 'completed_with_errors')
    except Exception as error:
        emit({'state': 'failed', 'error': str(error) if type(error) is ValueError else
              f'{type(error).__name__}：資料庫操作失敗；請核對環境與來源'})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
