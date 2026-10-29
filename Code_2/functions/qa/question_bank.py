"""問題向量持久快取；與文件切法、索引、題號及標準答案無關。"""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from Code_2.functions.embedding.providers import validate_vectors


def query_vector(settings, question, profile, generate):
    identity = {'schema': 'question-vector/1.0', 'model': profile,
                'query_encoding': 'voyage-query' if profile['backend'] == 'voyage' else 'bge-normalized',
                'question': question}
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    key = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    path = settings.question_bank_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS question_vectors '
                     '(cache_key TEXT PRIMARY KEY, identity TEXT NOT NULL, vector TEXT NOT NULL, '
                     'original_usage TEXT NOT NULL, created_at TEXT NOT NULL)')
        # 同時查同題也只生成一次；API失敗會rollback，不保存失敗向量。
        conn.execute('BEGIN IMMEDIATE')
        try:
            row = conn.execute('SELECT identity,vector,original_usage FROM question_vectors WHERE cache_key=?', (key,)).fetchone()
            if row:
                if row[0] != encoded:
                    raise ValueError('題庫識別不一致')
                vector = validate_vectors([json.loads(row[1])], expected_count=1, dimension=profile['dimension'])[0]
                usage = {'total_tokens': 0, 'api_called': False, 'reason': 'question_vector_cache_hit'}
            else:
                vector, usage = generate()
                vector = validate_vectors([vector], expected_count=1, dimension=profile['dimension'])[0]
                conn.execute('INSERT INTO question_vectors VALUES (?,?,?,?,?)',
                    (key, encoded, json.dumps(vector, allow_nan=False), json.dumps(usage, ensure_ascii=False),
                     datetime.now(timezone.utc).isoformat()))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return vector, usage, {'hit': bool(row), 'key': key, 'schema': 'question-vector/1.0'}
