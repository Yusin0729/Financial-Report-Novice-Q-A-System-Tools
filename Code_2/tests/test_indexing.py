"""實際Chroma暫存庫＋模擬模型，嚴格區分真實embedding品質。"""
import hashlib
import configparser
import json
import tempfile
import time
import gc
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from Code_2.config.embedding import Settings
from Code_2.functions.embedding.fields import load_rules, select_fields
from Code_2.functions.embedding.prepare import prepare_document
from Code_2.functions.embedding.indexing import build_document, embed_batch, recent_attempts
from Code_2.functions.embedding.providers import VoyageProvider, create_provider
from Code_2.functions.embedding.store import ChromaStore
from Code_2.functions.embedding.keys import voyage_key
from Code_2.tests.test_preparation import fixture


class FakeProvider:
    limit = 8192
    dimension = 2
    profile = {'backend': 'test-only', 'model': 'fake', 'dimension': 2, 'max_tokens': 8192}

    def __init__(self, counts=None):
        self.counts = counts
        self.calls = 0

    def count_tokens(self, texts):
        return self.counts or [10] * len(texts)

    def embed(self, texts, *, batch_size):
        self.calls += 1
        return [[0.6, 0.8] for _ in texts]


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='財報 索引 ')
        self.addCleanup(self.cleanup_temp)
        self.root = Path(self.tmp.name)
        self.settings = Settings(project_root=self.root)
        self.config = self.root / 'fields.txt'
        self.config.write_text('[FIELDS]\nembedding_text=embedding\nmetadata.stock_code=metadata\n'
                               'metadata.years=both\nmetadata.page=metadata\n'
                               'metadata.data_tags=metadata\n', encoding='utf-8')
        self.rules = load_rules(self.config)
        self.doc = prepare_document(fixture(), input_sha256='a' * 64)
        self.store = None

    def cleanup_temp(self):
        path = Path(self.tmp.name).resolve()
        if path.parent != Path(tempfile.gettempdir()).resolve() or not path.name.startswith('財報 索引 '):
            raise ValueError('測試清理路徑超出本次暫存目錄')
        # Rust/SQLite背景資源在Windows可能稍晚釋放；最多等1秒，不忽略清理失敗。
        for attempt in range(21):
            gc.collect()
            try:
                self.tmp.cleanup()
                return
            except PermissionError:
                if attempt == 20:
                    raise
                time.sleep(0.05)

    def factory(self, signature):
        self.store = ChromaStore(self.root / 'db', signature=signature)
        self.addCleanup(self.store.close)
        return self.store

    def build(self, doc=None, provider=None, digest='b' * 64, **kwargs):
        return build_document(doc or self.doc, prepared_sha256=digest, rules=self.rules,
                              provider=provider or FakeProvider(), batch_size=1, store_factory=self.factory, **kwargs)

    def test_four_roles_typed_fields_and_empty_filter(self):
        item = select_fields(self.doc['chunks'][0], self.rules)
        self.assertIn('years: 2025', item['text'])
        self.assertEqual(item['chroma_metadata']['years'], [2025])
        self.assertNotIn('report_year', item['chroma_metadata'])
        self.assertEqual(item['metadata']['data_tags'], [])
        self.assertNotIn('data_tags', item['chroma_metadata'])
        self.assertEqual(item['omitted_filter_fields'], ['metadata.data_tags'])

    def test_invalid_fields_or_mode_or_no_embedding(self):
        for content in ('[FIELDS]\nembedding_text=wrong', '[FIELDS]\nmetadata.page=metadata',
                        '[FIELDS]\nembedding_text=embedding\nembedding_text=both', '[OTHER]\na=embedding'):
            self.config.write_text(content, encoding='utf-8')
            with self.subTest(content=content), self.assertRaises((ValueError, configparser.Error)):
                load_rules(self.config)
        self.config.write_text('[FIELDS]\nembedding_text=embedding\nmetadata.typo=ignore', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '不存在'):
            select_fields(self.doc['chunks'][0], load_rules(self.config))

    def test_complex_metadata_rejected_not_stringified(self):
        self.config.write_text('[FIELDS]\nembedding_text=embedding\noriginal_chunk.title=metadata', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '不能直接當Chroma標籤'):
            select_fields(self.doc['chunks'][0], load_rules(self.config))

    def test_original_content_embedding_uses_pipe(self):
        raw = '<table><tr><td>(1,234.50)</td></tr></table>'
        doc = prepare_document(fixture(raw, 'table'), input_sha256='a' * 64)
        self.config.write_text('[FIELDS]\noriginal_chunk.content=embedding', encoding='utf-8')
        text = select_fields(doc['chunks'][0], load_rules(self.config))['text']
        self.assertIn('| (1,234.50) |', text)
        self.assertNotIn('<table>', text)

    def test_full_preflight_over_limit_never_writes_or_embeds(self):
        doc = deepcopy(self.doc)
        doc['chunks'].append(deepcopy(doc['chunks'][0]))
        doc['chunks'][1]['chunk_id'] = doc['chunks'][1]['original_chunk']['chunk_id'] = doc['doc_id'] + '__c00002'
        doc['chunks'][1]['metadata']['chunk_id'] = doc['chunks'][1]['chunk_id']
        provider = FakeProvider([10, 8193])
        result = self.build(doc, provider)
        self.assertEqual(result['status'], 'blocked_token_limit')
        self.assertEqual(result['over_limit'][0]['chunk_id'], doc['chunks'][1]['chunk_id'])
        self.assertEqual(provider.calls, 0)
        self.assertIsNone(self.store)

    def test_check_only_does_not_create_store(self):
        result = self.build(check_only=True)
        self.assertEqual(result['status'], 'checked')
        self.assertIsNone(self.store)

    def test_chroma_persistence_filters_and_full_source(self):
        result = self.build()
        self.assertEqual(result['status'], 'indexed')
        rows = self.store.search([0.6, 0.8], where={'$and': [{'years': {'$contains': 2025}}, {'page': {'$contains': 41}}]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['payload']['original_chunk'], self.doc['chunks'][0]['original_chunk'])
        self.assertEqual(self.store.search([0.6, 0.8], where={'stock_code': '2303'}), [])
        reopened = ChromaStore(self.root / 'db', signature=self.store.signature)
        self.addCleanup(reopened.close)
        self.assertEqual(len(reopened.search([0.6, 0.8])), 1)

    def test_repeat_is_skipped_without_embedding_and_new_version_rejected(self):
        self.build()
        provider = FakeProvider()
        result = self.build(provider=provider)
        self.assertEqual(result['status'], 'already_indexed')
        self.assertEqual(provider.calls, 0)
        with self.assertRaisesRegex(ValueError, '不同版本'):
            self.build(digest='c' * 64)
        self.assertEqual(self.store.collection.count(), 1)

    def test_field_changes_isolate_collections(self):
        self.build()
        first = self.store.collection_name
        self.config.write_text('[FIELDS]\nembedding_text=embedding\nmetadata.stock_code=both', encoding='utf-8')
        self.rules = load_rules(self.config)
        self.build()
        self.assertNotEqual(first, self.store.collection_name)

    def test_failed_encoder_does_not_store_partial_document(self):
        provider = FakeProvider()
        provider.embed = Mock(side_effect=RuntimeError('模擬錯誤'))
        with self.assertRaises(RuntimeError):
            self.build(provider=provider)
        self.assertEqual(self.store.collection.count(), 0)
        self.assertEqual(self.store.search([0.6, 0.8]), [])

    def test_partial_chroma_write_rolls_back_own_run(self):
        original_add = None
        def fail_factory(signature):
            store = self.factory(signature)
            nonlocal original_add
            original_add = store.collection.add
            def fail_after_add(**kwargs):
                original_add(**kwargs)
                raise OSError('模擬寫入後錯誤')
            store.collection.add = fail_after_add
            return store
        with self.assertRaises(OSError):
            build_document(self.doc, prepared_sha256='b' * 64, rules=self.rules, provider=FakeProvider(),
                           batch_size=1, store_factory=fail_factory)
        self.assertEqual(self.store.collection.count(), 0)
        self.assertEqual(self.store.search([0.6, 0.8]), [])

    def test_orphan_points_never_retrieved_or_automatically_deleted(self):
        self.build()
        self.store.collection.add(ids=['orphan'], embeddings=[[0.6, 0.8]],
                                  metadatas=[{'_sys_doc_id': 'other', '_sys_run_id': 'not-committed'}], documents=['{}'])
        self.assertEqual(len(self.store.search([0.6, 0.8])), 1)
        with self.assertRaisesRegex(ValueError, '未完成'):
            self.store.existing('other', 'hash', ['orphan'])
        self.assertEqual(self.store.collection.count(), 2)

    def test_batch_reports_and_saved_attempt(self):
        batch = self.settings.output_dir / 'Financial_20261022_01-23-16'
        (batch / 'Record').mkdir(parents=True)
        source = batch / '2025_2330_prepared.json'
        raw = json.dumps(self.doc, ensure_ascii=False).encode('utf-8')
        source.write_bytes(raw)
        record = {'status': 'prepared_needs_review', 'batch': batch.name, 'doc_id': self.doc['doc_id'],
                  'input_sha256': self.doc['input_sha256'], 'chunk_count': 1,
                  'outputs': {'json': {'filename': source.name, 'sha256': hashlib.sha256(raw).hexdigest()}}}
        (batch / 'Record/2025_2330_reocrd').write_text(json.dumps(record), encoding='utf-8')
        rows = embed_batch(batch, self.settings, backend='bge', fields_file=self.config,
                           provider_factory=lambda *args: FakeProvider([8193]))
        self.assertEqual(rows[0]['status'], 'blocked_token_limit')
        self.assertEqual(recent_attempts(self.settings, 'bge')[0]['over_limit'][0]['tokens'], 8193)

    def test_source_change_before_commit_does_not_store(self):
        def changed():
            raise ValueError('來源變更')
        with self.assertRaisesRegex(ValueError, '來源變更'):
            self.build(before_commit=changed)
        self.assertEqual(self.store.collection.count(), 0)

    def test_bad_token_counts_rejected(self):
        for counts in ([True], [0], [10, 20]):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                self.build(provider=FakeProvider(counts))

    def test_missing_settings_file_does_not_guess(self):
        self.config.unlink()
        with self.assertRaises(FileNotFoundError):
            load_rules(self.config)

    def test_duplicate_filter_names_rejected(self):
        self.config.write_text('[FIELDS]\nembedding_text=embedding\nmetadata.main_title=metadata\n'
                               'original_chunk.title.main_title=metadata', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '重複'):
            select_fields(self.doc['chunks'][0], load_rules(self.config))


class VoyageTests(unittest.TestCase):
    def test_request_error_does_not_echo_body(self):
        client = Mock()
        client.count_tokens.return_value = 10
        client.embed.side_effect = RuntimeError('PRIVATE-KEY financial-full-text')
        p = VoyageProvider(client=client, model_name='voyage-finance-2', max_tokens=32000, batch_tokens=120000)
        with self.assertRaises(RuntimeError) as context:
            p.embed(['財報'], batch_size=1)
        self.assertNotIn('PRIVATE-KEY', str(context.exception))
        self.assertNotIn('financial-full-text', str(context.exception))

    def test_document_prefix_no_truncation_and_vectors(self):
        client = Mock()
        client.count_tokens.return_value = 10
        client.embed.return_value = SimpleNamespace(embeddings=[[1.0] + [0.0] * 1023])
        p = VoyageProvider(client=client, model_name='voyage-finance-2', max_tokens=32000, batch_tokens=120000)
        self.assertEqual(len(p.embed(['財報'], batch_size=1)[0]), 1024)
        self.assertEqual(client.embed.call_args.kwargs['input_type'], 'document')
        self.assertFalse(client.embed.call_args.kwargs['truncation'])
        self.assertIn('Represent the document for retrieval: ', client.count_tokens.call_args.args[0][0])

    def test_api_disabled_before_key_read_or_client_creation(self):
        with patch('Code_2.functions.embedding.keys.voyage_key') as key:
            with self.assertRaisesRegex(ValueError, '尚未啟用'):
                create_provider('voyage', Settings())
            key.assert_not_called()

    def test_batch_over_limit_never_sends(self):
        client = Mock()
        client.count_tokens.return_value = 32001
        p = VoyageProvider(client=client, model_name='voyage-finance-2', max_tokens=32000, batch_tokens=120000)
        with self.assertRaises(ValueError):
            p.embed(['長表格'], batch_size=1)
        client.embed.assert_not_called()

    def test_only_voyage_env_field_is_parsed_no_expansion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.env').write_text('OTHER_KEY=do-not-load\nVOYAGE_API_KEY="${UNRELATED}"\n', encoding='utf-8')
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual(voyage_key(root), '${UNRELATED}')


if __name__ == '__main__':
    unittest.main()
