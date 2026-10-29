"""整集合移除：只讀提交清冊與集合設定，不讀取HNSW向量；支援中斷後重試。"""
import hashlib
import json
import re
import sqlite3
from contextlib import closing


def collection_pending(conn, name):
    if not conn.execute("SELECT name FROM sqlite_master WHERE name='collection_deletions'").fetchone():
        return None
    row = conn.execute('SELECT signature FROM collection_deletions WHERE collection=?', (name,)).fetchone()
    return json.loads(row[0]) if row else None


def ensure_collection_active(conn, name):
    if collection_pending(conn, name) is not None:
        raise ValueError('此集合正在整組移除，請先在資料庫管理重新預覽並完成移除')


def _root(settings, backend, collection):
    if backend not in ('bge', 'voyage') or not isinstance(collection, str) or not re.fullmatch(r'financial_[a-f0-9]{24}', collection):
        raise ValueError('請選有效模型與索引集合')
    root = settings.vector_root / backend
    if not (root / 'ingestion.sqlite3').is_file() or not (root / 'chroma.sqlite3').is_file():
        raise ValueError('索引資料庫不存在，不會建立空庫')
    return root


def _client(root):
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(root), settings=Settings(anonymized_telemetry=False))


def _snapshot(conn, root, backend, collection):
    rows = conn.execute('SELECT doc_id,content_hash,run_id,chunk_count,created_at FROM documents '
                        'WHERE collection=? ORDER BY doc_id', (collection,)).fetchall()
    if not rows:
        raise ValueError('此集合沒有已提交財報，請更新清單；不處理未知的孤立資料')
    signature = collection_pending(conn, collection)
    pending = signature is not None
    if not pending:
        with closing(_client(root)) as client:
            item = client.get_collection(collection, embedding_function=None)
            signature = json.loads((item.metadata or {}).get('signature', '{}'))
    if signature.get('model', {}).get('backend') != backend:
        raise ValueError('索引模型與儲存位置不符')
    encoded = json.dumps(signature, sort_keys=True, ensure_ascii=False)
    if 'financial_' + hashlib.sha256(encoded.encode()).hexdigest()[:24] != collection:
        raise ValueError('索引設定與集合名稱不符，未移除')
    parents = 0
    if conn.execute("SELECT name FROM sqlite_master WHERE name='table_parents'").fetchone():
        parents = conn.execute('SELECT count(*) FROM table_parents WHERE collection=?', (collection,)).fetchone()[0]
    digest = hashlib.sha256(json.dumps([backend, collection, signature, rows, parents], sort_keys=True,
                                      ensure_ascii=False).encode()).hexdigest()
    return {'backend': backend, 'collection': collection, 'signature': signature,
            'documents': [{'doc_id': r[0], 'chunk_count': r[3]} for r in rows],
            'chunk_count': sum(r[3] for r in rows), 'parent_count': parents,
            'count_source': 'registry', 'pending': pending, 'token': digest}


def collection_snapshot(settings, backend, collection):
    root = _root(settings, backend, collection)
    with closing(sqlite3.connect(root / 'ingestion.sqlite3', timeout=0)) as conn:
        return _snapshot(conn, root, backend, collection)


def _delete_native(client, collection):
    from chromadb.errors import NotFoundError
    try:
        client.delete_collection(collection)
    except NotFoundError:
        pass  # 只在先前已寫入整組移除標記後呼叫，允許原生刪除已完成的重試。
    try:
        client.get_collection(collection, embedding_function=None)
    except NotFoundError:
        return
    raise ValueError('集合仍存在，未完成整組移除；請重新預覽後重試')


def delete_collection(settings, backend, collection, token):
    root = _root(settings, backend, collection)
    with closing(sqlite3.connect(root / 'ingestion.sqlite3', timeout=0, isolation_level=None)) as conn:
        conn.execute('BEGIN IMMEDIATE')
        try:
            preview = _snapshot(conn, root, backend, collection)
            if not isinstance(token, str) or token != preview['token']:
                raise ValueError('集合移除預覽已過期，請重新預覽')
            conn.execute('CREATE TABLE IF NOT EXISTS collection_deletions(collection TEXT PRIMARY KEY, signature TEXT)')
            conn.execute('CREATE TABLE IF NOT EXISTS deletions(collection TEXT, doc_id TEXT, run_id TEXT, PRIMARY KEY(collection,doc_id))')
            conn.execute('INSERT OR REPLACE INTO collection_deletions VALUES (?,?)',
                         (collection, json.dumps(preview['signature'], ensure_ascii=False)))
            conn.execute('INSERT OR REPLACE INTO deletions SELECT collection,doc_id,run_id FROM documents WHERE collection=?', (collection,))
            conn.commit()  # 先阻擋建庫與召回，原生刪除失敗時保留以供重試。
        except BaseException:
            conn.rollback()
            raise
    with closing(_client(root)) as client:
        _delete_native(client, collection)
    with closing(sqlite3.connect(root / 'ingestion.sqlite3', timeout=0, isolation_level=None)) as conn:
        conn.execute('BEGIN IMMEDIATE')
        try:
            if conn.execute("SELECT name FROM sqlite_master WHERE name='table_parents'").fetchone():
                conn.execute('DELETE FROM table_parents WHERE collection=?', (collection,))
            conn.execute('DELETE FROM documents WHERE collection=?', (collection,))
            conn.execute('DELETE FROM deletions WHERE collection=?', (collection,))
            conn.execute('DELETE FROM collection_deletions WHERE collection=?', (collection,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return {'deleted': [d['doc_id'] for d in preview['documents']], 'collection': collection,
            'chunk_count': preview['chunk_count'], 'count_source': 'registry'}
