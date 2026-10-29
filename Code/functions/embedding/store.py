"""Chroma持久儲存及提交清冊；不依賴實驗Output取回原文。

每份完成全部向量後才寫入；以SQLite提交清冊限制查詢只看已提交文件。
不同模型／欄位規則分collection。同文件改版先拒絕，不擅自刪舊索引。
"""
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from Code.functions.parent_relations import LINKS, contains
from Code.functions.embedding.collection_management import ensure_collection_active


class ChromaStore:
    def __init__(self, path, *, signature, create=True):
        import chromadb
        from chromadb.config import Settings
        self.path, self.signature = path, signature
        encoded = json.dumps(signature, sort_keys=True, ensure_ascii=False)
        self.collection_name = 'financial_' + hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]
        registry = path / 'ingestion.sqlite3'
        if registry.is_file():
            with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as conn:
                ensure_collection_active(conn, self.collection_name)
        self.client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
        if create:
            self.collection = self.client.get_or_create_collection(
                self.collection_name, embedding_function=None,
                metadata={'signature': encoded}, configuration={'hnsw': {'space': 'cosine'}})
        else:
            self.collection = self.client.get_collection(self.collection_name, embedding_function=None)
        if self.collection.metadata.get('signature') != encoded:
            raise ValueError('collection設定與模型／欄位規則不符')
        self.registry = path / 'ingestion.sqlite3'
        if create:
            with closing(self.connect()) as conn:
                conn.execute('CREATE TABLE IF NOT EXISTS documents(collection TEXT, doc_id TEXT, content_hash TEXT, '
                             'run_id TEXT, chunk_count INTEGER, created_at TEXT, PRIMARY KEY(collection,doc_id))')
                conn.execute('CREATE TABLE IF NOT EXISTS table_parents(collection TEXT, run_id TEXT, parent_id TEXT, '
                             'doc_id TEXT, payload TEXT, PRIMARY KEY(collection,run_id,parent_id))')

    def connect(self):
        return sqlite3.connect(self.registry, timeout=0, isolation_level=None)

    def close(self):
        """使用鎖定版本的公開close釋放Windows檔案鎖，不清除資料。"""
        self.collection = None
        self.client.close()

    def existing(self, doc_id, content_hash, ids, conn=None):
        if conn is None:
            with closing(self.connect()) as own:
                return self.existing(doc_id, content_hash, ids, own)
        ensure_collection_active(conn, self.collection_name)
        if conn.execute("SELECT name FROM sqlite_master WHERE name='deletions'").fetchone():
            if conn.execute('SELECT 1 FROM deletions WHERE collection=? AND doc_id=?', (self.collection_name, doc_id)).fetchone():
                raise ValueError('文件刪除尚未完成，請先由資料管理重試刪除')
        row = conn.execute('SELECT content_hash,run_id,chunk_count FROM documents WHERE collection=? AND doc_id=?',
                           (self.collection_name, doc_id)).fetchone()
        actual = self.collection.get(where={'_sys_doc_id': doc_id}, include=['metadatas', 'documents'])
        if row is None:
            if actual['ids']:
                raise ValueError('存在未完成／未提交的索引，未自動清除；請先確認恢復方式')
            return False
        if row[0] != content_hash:
            raise ValueError('同文件已有不同版本，未覆寫舊索引；請先確認更新或移除方式')
        if (row[2] != len(ids) or set(actual['ids']) != set(ids) or
                any(m.get('_sys_run_id') != row[1] for m in actual['metadatas'])):
            raise ValueError('索引與提交清冊不完整，不能當作已成功匯入')
        for raw in actual['documents']:
            chunk = json.loads(raw)['original_chunk']
            for field,_ in LINKS:
                parent_id = chunk.get(field)
                if parent_id is None:
                    continue
                parent = conn.execute('SELECT payload FROM table_parents WHERE collection=? AND run_id=? '
                                      'AND parent_id=? AND doc_id=?',
                                      (self.collection_name, row[1], parent_id, doc_id)).fetchone()
                if parent is None or not contains(json.loads(parent[0]),chunk):
                    raise ValueError('已提交索引的完整父表缺失或不符，不能略過匯入')
        return True

    def commit_document(self, *, doc_id, content_hash, items, vectors, model_profile, input_sha256):
        from Code.functions.embedding.providers import validate_vectors
        vectors = validate_vectors(vectors, expected_count=len(items), dimension=model_profile['dimension'])
        ids = [item['chunk_id'] for item in items]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError('空文件或chunk_id重複')
        with closing(self.connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')  # 不同程序不可同時改同一模型庫的清冊。
            run = uuid.uuid4().hex
            attempted = False
            try:
                if self.existing(doc_id, content_hash, ids, conn):
                    conn.rollback()
                    return False
                metadatas, documents = [], []
                parents = {}
                for item in items:
                    for field,payload_field in LINKS:
                        parent_id = item['original_chunk'].get(field)
                        if parent_id is None:
                            continue
                        parent = item.get(payload_field)
                        if not isinstance(parent, dict) or parent.get('chunk_id') != parent_id or parent.get('doc_id') != doc_id:
                            raise ValueError('缺少完整父表，未提交子塊')
                        if not contains(parent,item['original_chunk']):
                            raise ValueError('完整父項與搜尋子項來源錯配')
                        encoded = json.dumps(parent, ensure_ascii=False)
                        if parent_id in parents and parents[parent_id] != encoded:
                            raise ValueError('同一父表內容不一致')
                        parents[parent_id] = encoded
                    metadatas.append({**item['chroma_metadata'], '_sys_doc_id': doc_id,
                                      '_sys_chunk_id': item['chunk_id'], '_sys_run_id': run,
                                      '_sys_input_sha256': input_sha256})
                    documents.append(json.dumps({'schema_version': 'financial-vector-payload/1.0',
                                                 'embedding_text': item['text'], 'metadata': item['metadata'],
                                                 'original_chunk': item['original_chunk'],
                                                 'model': model_profile, 'input_sha256': input_sha256},
                                                ensure_ascii=False))
                for parent_id, encoded in parents.items():
                    conn.execute('INSERT INTO table_parents VALUES (?,?,?,?,?)',
                                 (self.collection_name, run, parent_id, doc_id, encoded))
                size = self.client.get_max_batch_size()
                for start in range(0, len(ids), size):
                    end = start + size
                    attempted = True
                    self.collection.add(ids=ids[start:end], embeddings=vectors[start:end],
                                        documents=documents[start:end], metadatas=metadatas[start:end])
                written = self.collection.get(where={'_sys_run_id': run}, include=['metadatas'])
                if set(written['ids']) != set(ids):
                    raise ValueError('Chroma寫入數量不符，未提交文件')
                conn.execute('INSERT INTO documents VALUES (?,?,?,?,?,?)',
                             (self.collection_name, doc_id, content_hash, run, len(ids),
                              datetime.now(timezone.utc).isoformat()))
                conn.commit()
                return True
            except BaseException:
                conn.rollback()
                if attempted:
                    # 只移除此呼叫新建run的資料，絕不清空整庫或其他文件。
                    self.collection.delete(where={'_sys_run_id': run})
                raise

    def search(self, query_vector, *, n_results=5, where=None):
        """僅供檢索層整合；只召回已提交文件，回傳完整原文與cosine距離。"""
        with closing(self.connect()) as conn:
            ensure_collection_active(conn, self.collection_name)
            pending = conn.execute("SELECT name FROM sqlite_master WHERE name='deletions'").fetchone()
            sql = 'SELECT run_id,chunk_count FROM documents WHERE collection=?'
            if pending:
                sql += ' AND NOT EXISTS (SELECT 1 FROM deletions d WHERE d.collection=documents.collection AND d.doc_id=documents.doc_id)'
            committed = conn.execute(sql, (self.collection_name,)).fetchall()
        if not committed:
            return []
        gate = {'_sys_run_id': {'$in': [row[0] for row in committed]}}
        constraint = {'$and': [gate, where]} if where else gate
        result = self.collection.query(query_embeddings=[query_vector], where=constraint,
                                       n_results=min(n_results, sum(row[1] for row in committed)),
                                       include=['documents', 'metadatas', 'distances'])
        rows = [{'chunk_id': cid, 'distance': distance, 'metadata': meta, 'payload': json.loads(payload)}
                for cid, distance, meta, payload in zip(result['ids'][0], result['distances'][0],
                                                      result['metadatas'][0], result['documents'][0])]
        with closing(self.connect()) as conn:
            for row in rows:
                for field,payload_field in LINKS:
                    parent_id = row['payload']['original_chunk'].get(field)
                    if parent_id is None:
                        continue
                    found = conn.execute('SELECT payload FROM table_parents WHERE collection=? AND run_id=? '
                                     'AND parent_id=? AND doc_id=?',
                                     (self.collection_name, row['metadata']['_sys_run_id'], parent_id,
                                      row['metadata']['_sys_doc_id'])).fetchone()
                    if found is None:
                        raise ValueError('子塊的完整父項遺失，不能當作完整證據')
                    row['payload'][payload_field] = json.loads(found[0])
        return rows
