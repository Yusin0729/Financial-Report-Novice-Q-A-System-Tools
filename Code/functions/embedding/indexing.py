"""前檢整份文件、計算向量、提交Chroma；不把整份JSON送給模型。"""
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from Code.config.embedding import INDEX_RULE
from Code.functions.embedding.fields import load_rules, select_fields
from Code.functions.embedding.load_prepared import prepared_sources, load_prepared, validate_prepared
from Code.functions.embedding.providers import create_provider
from Code.functions.embedding.store import ChromaStore
from Code.functions.embedding.paths import outer_batch


def build_document(doc, *, prepared_sha256, rules, provider, batch_size, store_factory, check_only=False,
                   before_commit=None, index_target=None):
    validate_prepared(doc)
    items = [select_fields(item, rules) for item in doc['chunks']]
    parents = {p['chunk_id']: p for p in doc.get('parents', [])}
    for item in items:
        item['original_parent'] = parents.get(item['original_chunk'].get('parent_id'))
        item['original_heading_parent'] = parents.get(item['original_chunk'].get('heading_parent_id'))
    texts = [item['text'] for item in items]
    counts = provider.count_tokens(texts)
    if len(counts) != len(items) or any(type(c) is not int or c < 1 for c in counts):
        raise ValueError('token計數筆數或型別不符')
    result = {'doc_id': doc['doc_id'], 'chunk_count': len(items), 'model': provider.profile,
              'fields_fingerprint': rules.fingerprint, 'fields_file_sha256': rules.sha256,
              'fields': list(rules.entries), 'prepared_sha256': prepared_sha256,
              'token_total': sum(counts), 'token_max': max(counts), 'check_only': check_only,
              'token_counts': [{'chunk_id': item['chunk_id'], 'tokens': count} for item, count in zip(items, counts)],
              'omitted_filter_fields': sorted(set(p for item in items for p in item['omitted_filter_fields']))}
    over = [{'chunk_id': item['chunk_id'], 'tokens': count, 'limit': provider.limit}
            for item, count in zip(items, counts) if count > provider.limit]
    if over:
        return {**result, 'status': 'blocked_token_limit', 'over_limit': over, 'written': 0}
    if check_only:
        return {**result, 'status': 'checked', 'written': 0}
    signature = {'rule': INDEX_RULE, 'model': provider.profile, 'fields': list(rules.entries),
                 'preparation_rule': doc['rule_version']}
    if 'embedding_context_modes' in doc:
        signature['embedding_context_modes'] = doc['embedding_context_modes']
        result['embedding_context_modes'] = doc['embedding_context_modes']
    if 'chunking' in doc:
        signature['chunking'] = doc['chunking']
        signature['source_chunk_rule'] = doc.get('source_rule_version')
    from Code.functions.embedding.index_target import bind_signature
    signature = bind_signature(signature, index_target)
    store = store_factory(signature)
    content_hash = hashlib.sha256((prepared_sha256 + rules.fingerprint).encode()).hexdigest()
    ids = [item['chunk_id'] for item in items]
    result.update(collection=store.collection_name, display_name=signature.get('experiment', {}).get('name', store.collection_name))
    if store.existing(doc['doc_id'], content_hash, ids):
        return {**result, 'status': 'already_indexed', 'written': 0}
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError('模型批次大小必須為正整數')
    vectors, start = [], 0
    while start < len(items):
        end = start
        budget = getattr(provider, 'batch_tokens', None)
        while end < len(items) and end - start < batch_size:
            if budget is not None and sum(counts[start:end + 1]) > budget:
                break
            end += 1
        if end == start:
            raise ValueError('單筆超過請求批次token預算，未送出')
        print(f'向量化 {doc["doc_id"]}：{start + 1}–{end}/{len(items)}', flush=True)
        vectors.extend(provider.embed(texts[start:end], batch_size=batch_size))
        start = end
    if before_commit is not None:
        before_commit()
    committed = store.commit_document(doc_id=doc['doc_id'], content_hash=content_hash, items=items,
                                      vectors=vectors, model_profile=provider.profile,
                                      input_sha256=prepared_sha256)
    return {**result, 'status': 'indexed' if committed else 'already_indexed',
            'written': len(items) if committed else 0}


def save_attempt(root, record):
    """必要索引操作清冊，無財報全文／金鑰；不是實驗Output產物。"""
    root.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root / 'ingestion.sqlite3')) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, created_at TEXT, record TEXT)')
        conn.execute('INSERT INTO attempts(created_at,record) VALUES (?,?)',
                     (datetime.now(timezone.utc).isoformat(), json.dumps(record, ensure_ascii=False)))
        conn.commit()


def recent_attempts(settings, backend, limit=10):
    path = settings.vector_root / backend / 'ingestion.sqlite3'
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        if not conn.execute("SELECT name FROM sqlite_master WHERE name='attempts'").fetchone():
            return []
        return [json.loads(row[0]) for row in conn.execute('SELECT record FROM attempts ORDER BY id DESC LIMIT ?', (limit,))]


def embed_batch(path, settings, *, backend, fields_file=None, check_only=False,
                provider_factory=create_provider, store_class=ChromaStore):
    if backend not in ('bge', 'voyage', 'both'):
        raise ValueError('backend須為bge／voyage／both')
    sources = prepared_sources(path, settings)
    fields_file = Path(fields_file or settings.fields_file)
    rules = load_rules(fields_file)
    backends = ('bge', 'voyage') if backend == 'both' else (backend,)
    outcomes = []
    for name in backends:
        provider = None
        for source in sources:
            started = time.perf_counter()
            opened = []
            record = {'schema_version': 'embedding-index-run/1.0', 'backend': name,
                      'batch': outer_batch(source), 'source_file': source.name, 'status': 'failed'}
            try:
                if source.resolve().parent != source.parent.resolve():
                    raise ValueError('來源連結超出批次')
                doc, digest, origin = load_prepared(source)
                # 先驗證欄位，拼字錯誤不能觸發模型下載或API。
                for item in doc['chunks']:
                    select_fields(item, rules)
                record.update(doc_id=doc['doc_id'], temporary_fallback=origin.get('temporary_fallback'),
                              source_record_issue=origin.get('source_record_issue'))
                if provider is None:
                    print(f'準備模型 {name}；第一次使用可能需要下載本機權重／tokenizer。', flush=True)
                    provider = provider_factory(name, settings)
                if hashlib.sha256(fields_file.read_bytes()).hexdigest() != rules.sha256:
                    raise ValueError('欄位設定在處理期間變更，未開始該份文件')
                size = settings.bge_batch_size if name == 'bge' else settings.voyage_batch_size
                def open_store(signature):
                    store = store_class(settings.vector_root / name, signature=signature)
                    opened.append(store)
                    return store
                def verify_source():
                    if (hashlib.sha256(source.read_bytes()).hexdigest() != digest or
                            hashlib.sha256(fields_file.read_bytes()).hexdigest() != rules.sha256):
                        raise ValueError('來源或欄位設定在向量化期間變更，未提交文件')
                record.update(build_document(doc, prepared_sha256=digest, rules=rules, provider=provider,
                                              batch_size=size, check_only=check_only,
                                              store_factory=open_store, before_commit=verify_source))
            except KeyboardInterrupt:
                record.update(status='interrupted', error='使用者中止；未提交的文件不會參與檢索')
            except Exception as error:
                record.update(status='failed', error=f'{type(error).__name__}: {error}')
            finally:
                for store in reversed(opened):
                    store.close()
            record['elapsed_seconds'] = round(time.perf_counter() - started, 6)
            if not check_only:
                save_attempt(settings.vector_root / name, record)
            print(f'{name}／{source.name}：{record["status"]}', flush=True)
            if 'token_max' in record:
                print(f'共{record["chunk_count"]}筆；最大{record["token_max"]} tokens，總計{record["token_total"]} tokens。')
            for over in record.get('over_limit', []):
                print(f'超限：{over["chunk_id"]}，{over["tokens"]} tokens，上限{over["limit"]}；該份未寫入。')
            if 'error' in record:
                print(record['error'])
            outcomes.append(record)
            if record['status'] == 'interrupted':
                return outcomes
        del provider  # 預設依序執行模型，不同時常駐兩個模型。
    return outcomes
