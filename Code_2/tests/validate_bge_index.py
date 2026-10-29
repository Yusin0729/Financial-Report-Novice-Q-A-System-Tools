"""既有BGE真實索引核對：不重建索引，會本機計算一筆驗證問題的向量。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Code_2.config.embedding import Settings, INDEX_RULE
from Code_2.functions.embedding.fields import load_rules
from Code_2.functions.embedding.load_prepared import load_prepared
from Code_2.functions.embedding.providers import create_provider
from Code_2.functions.embedding.store import ChromaStore


def validate(source):
    settings = Settings()
    doc, digest, _ = load_prepared(source)
    rules = load_rules(settings.fields_file)
    provider = create_provider('bge', settings)
    signature = {'rule': INDEX_RULE, 'model': provider.profile, 'fields': list(rules.entries),
                 'preparation_rule': doc['rule_version']}
    store = ChromaStore(settings.vector_root / 'bge', signature=signature, create=False)
    try:
        ids = [item['chunk_id'] for item in doc['chunks']]
        content_hash = hashlib.sha256((digest + rules.fingerprint).encode()).hexdigest()
        if not store.existing(doc['doc_id'], content_hash, ids):
            raise ValueError('指定文件尚未完成索引')
        fetched = store.collection.get(ids=ids, include=['documents', 'metadatas', 'embeddings'])
        originals = {item['chunk_id']: item['original_chunk'] for item in doc['chunks']}
        embeddings = {}
        for cid, payload, vector, meta in zip(fetched['ids'], fetched['documents'], fetched['embeddings'], fetched['metadatas']):
            if json.loads(payload)['original_chunk'] != originals[cid] or len(vector) != 1024:
                raise ValueError('資料庫原文或向量維度不符')
            if abs(sum(float(v) ** 2 for v in vector) - 1.0) > 0.001:
                raise ValueError('儲存向量的正規化範數不符')
            embeddings[cid] = list(map(float, vector))
            if 'report_year' in meta or any(type(p) is not int for p in meta['page'] + meta['years']):
                raise ValueError('資料庫年份或頁碼型別不符')
        query = '台積公司成立時間及主要營運據點在哪裡？'
        vector = provider.embed([query], batch_size=1)[0]
        stock = doc['chunks'][0]['metadata']['stock_code']
        rows = store.search(vector, n_results=5, where={'stock_code': stock})
        expected = doc['doc_id'] + '__c00001'
        if not any(row['chunk_id'] == expected for row in rows):
            raise ValueError('公司沿革問題未在前五筆召回預期來源，需核對品質')
        multi = next((item for item in doc['chunks'] if item['original_chunk']['content_type'] == 'table'
                      and len(item['metadata']['page']) > 1), None)
        filtered = None
        if multi:
            target_page = multi['metadata']['page'][1]
            hits = store.search(embeddings[multi['chunk_id']], where={'$and': [
                {'page': {'$contains': target_page}},
                {'years': {'$contains': multi['metadata']['years'][0]}}]})
            if not any(row['chunk_id'] == multi['chunk_id'] for row in hits):
                raise ValueError('實際頁碼清單／年份數值篩選失敗')
            filtered = {'chunk_id': multi['chunk_id'], 'page_contains': target_page, 'year_range_filter': True}
        return {'status': 'validated', 'collection': store.collection_name, 'chunk_count': len(ids),
                'dimension': 1024, 'original_chunks_equal': True, 'metadata_types_valid': True,
                'typed_filter_test': filtered,
                'query_test': '公司沿革單題前五筆召回', 'expected_source': expected,
                'retrieved': [{'chunk_id': row['chunk_id'], 'page': row['payload']['original_chunk']['page'],
                               'distance': row['distance']} for row in rows]}
    finally:
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.source), ensure_ascii=False, indent=2))
