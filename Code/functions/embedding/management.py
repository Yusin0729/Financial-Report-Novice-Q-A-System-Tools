"""索引內整份文件的瀏覽／刪除；以預覽快照確認範圍，失敗保留刪除中狀態。"""
import hashlib
import json
import re
from contextlib import closing
from Code.functions.embedding.catalog import list_indexes, select_index
from Code.functions.embedding.store import ChromaStore
from Code.functions.embedding.collection_management import ensure_collection_active


def open_index(settings, backend, collection):
    if backend not in ('bge', 'voyage') or not isinstance(collection, str) or not re.fullmatch(r'financial_[a-f0-9]{24}', collection):
        raise ValueError('請選有效模型與索引')
    index = select_index(list_indexes(settings, backend), backend, collection)
    return ChromaStore(settings.vector_root / backend, signature=index['signature'], create=False)


def documents(store, *, doc_id='', stock_code='', year=None):
    if not isinstance(doc_id, str) or not isinstance(stock_code, str):
        raise ValueError('文件及股票篩選格式無效')
    if year is not None and (type(year) is not int or not 1900 <= year <= 2199):
        raise ValueError('年度須為1900至2199整數')
    with closing(store.connect()) as conn:
        rows = conn.execute('SELECT doc_id,run_id,chunk_count,created_at FROM documents WHERE collection=? ORDER BY doc_id',
                            (store.collection_name,)).fetchall()
        pending = set()
        if conn.execute("SELECT name FROM sqlite_master WHERE name='deletions'").fetchone():
            pending = {r[0] for r in conn.execute('SELECT doc_id FROM deletions WHERE collection=?', (store.collection_name,))}
    result = []
    for identity, run, count, created in rows:
        if doc_id and doc_id not in identity:
            continue
        actual = store.collection.get(where={'_sys_run_id': run}, include=['documents'])
        payloads = [json.loads(raw) for raw in actual['documents']]
        stocks = sorted({p['metadata']['stock_code'] for p in payloads})
        years = sorted({y for p in payloads for y in p['metadata'].get('years', [])})
        if (stock_code and stock_code not in stocks) or (year is not None and year not in years):
            continue
        result.append({'doc_id': identity, 'run_id': run, 'chunk_count': count,
                       'actual_chunk_count': len(actual['ids']), 'stock_codes': stocks, 'years': years,
                       'created_at': created, 'status': 'deletion_pending' if identity in pending else 'committed'})
    return result


def snapshot(store, ids):
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('請勾選不重複的doc_id')
    found = [r for r in documents(store) if r['doc_id'] in ids]
    if {r['doc_id'] for r in found} != set(ids):
        raise ValueError('文件已變更或不存在，請重新整理')
    digest = hashlib.sha256(json.dumps([store.collection_name, found], sort_keys=True).encode()).hexdigest()
    return {'documents': found, 'token': digest, 'chunk_count': sum(r['actual_chunk_count'] for r in found)}


def delete_documents(store, ids, token):
    preview = snapshot(store, ids)
    if preview['token'] != token:
        raise ValueError('刪除預覽已過期，請重新預覽')
    deleted = []
    for row in preview['documents']:
        identity, run = row['doc_id'], row['run_id']
        with closing(store.connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            ensure_collection_active(conn, store.collection_name)
            conn.execute('CREATE TABLE IF NOT EXISTS deletions(collection TEXT, doc_id TEXT, run_id TEXT, PRIMARY KEY(collection,doc_id))')
            current = conn.execute('SELECT run_id FROM documents WHERE collection=? AND doc_id=?', (store.collection_name, identity)).fetchone()
            if current != (run,):
                conn.rollback()
                raise ValueError('文件在刪除前已變更，請重新預覽')
            conn.execute('INSERT OR REPLACE INTO deletions VALUES (?,?,?)', (store.collection_name, identity, run))
            conn.commit()  # 先停用召回；後續失敗時不讓殘存片段參與問答。
        store.collection.delete(where={'_sys_doc_id': identity})
        if store.collection.get(where={'_sys_doc_id': identity}, include=[])['ids']:
            raise ValueError('向量刪除不完整；文件保持刪除中，可重新預覽後重試')
        with closing(store.connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute("SELECT name FROM sqlite_master WHERE name='table_parents'").fetchone():
                conn.execute('DELETE FROM table_parents WHERE collection=? AND doc_id=?', (store.collection_name, identity))
            conn.execute('DELETE FROM documents WHERE collection=? AND doc_id=? AND run_id=?', (store.collection_name, identity, run))
            conn.execute('DELETE FROM deletions WHERE collection=? AND doc_id=?', (store.collection_name, identity))
            conn.commit()
        deleted.append(identity)
    return {'deleted': deleted, 'chunk_count': preview['chunk_count']}


def browse_chunks(store, doc_id, offset=0):
    if type(offset) is not int or offset < 0:
        raise ValueError('分頁位置無效')
    row = next((r for r in documents(store) if r['doc_id'] == doc_id), None)
    if row is None:
        raise ValueError('文件不存在')
    data = store.collection.get(where={'_sys_run_id': row['run_id']}, limit=20, offset=offset,
                                include=['documents'])
    return {'total': row['actual_chunk_count'], 'offset': offset,
            'chunks': [{'chunk_id': cid, **json.loads(raw)} for cid, raw in zip(data['ids'], data['documents'])]}
