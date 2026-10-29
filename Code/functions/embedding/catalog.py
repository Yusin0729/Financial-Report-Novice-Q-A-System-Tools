"""從已提交索引選擇collection，不依賴prepared／chunk實驗檔。"""
import json
import sqlite3
from contextlib import closing
from Code.functions.embedding.collection_management import collection_pending


def list_indexes(settings, backend=None):
    import chromadb
    from chromadb.config import Settings
    result = []
    for name in ((backend,) if backend else ('bge', 'voyage')):
        if name not in ('bge', 'voyage'):
            raise ValueError('索引模型須為bge或voyage')
        root = settings.vector_root / name
        registry = root / 'ingestion.sqlite3'
        if not registry.is_file() or not (root / 'chroma.sqlite3').is_file():
            continue
        with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as conn:
            if not conn.execute("SELECT name FROM sqlite_master WHERE name='documents'").fetchone():
                continue
            rows = conn.execute('SELECT collection,doc_id,chunk_count FROM documents ORDER BY collection,doc_id').fetchall()
            pending = {r[0]: value for r in rows if (value := collection_pending(conn, r[0])) is not None}
        if not rows:
            continue
        client = chromadb.PersistentClient(path=str(root), settings=Settings(anonymized_telemetry=False))
        try:
            for collection_name in sorted({r[0] for r in rows}):
                signature = pending.get(collection_name)
                if signature is None:
                    collection = client.get_collection(collection_name, embedding_function=None)
                    signature = json.loads((collection.metadata or {}).get('signature', '{}'))
                if signature.get('model', {}).get('backend') != name:
                    raise ValueError('索引模型與儲存位置不符')
                docs = [r for r in rows if r[0] == collection_name]
                item = {'backend': name, 'collection': collection_name, 'signature': signature,
                        'doc_ids': [r[1] for r in docs], 'chunk_count': sum(r[2] for r in docs),
                        'display_name': signature.get('experiment', {}).get('name', collection_name)}
                modes = signature.get('embedding_context_modes')
                if modes:
                    labels = {'body':'純正文', 'description':'說明', 'full':'完整標籤'}
                    item['display_name'] += f"｜文字：{labels[modes['text']]}／表格：{labels[modes['table']]}"
                if collection_name in pending:
                    item['status'] = 'collection_deletion_pending'
                result.append(item)
        finally:
            client.close()
    return result


def select_index(indexes, backend, collection=None):
    found = [i for i in indexes if i['backend'] == backend and (collection is None or i['collection'] == collection)]
    if len(found) != 1:
        raise ValueError('找不到唯一已提交索引；請先建庫，或用--collection指定列出的collection')
    return found[0]
