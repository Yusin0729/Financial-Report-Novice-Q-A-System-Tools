"""實際暫存Chroma＋假向量，驗證完整父表召回與內容年度篩選。"""
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from Code_2.functions.embedding.prepare import prepare_document
from Code_2.functions.embedding.load_prepared import validate_prepared
from Code_2.functions.embedding.indexing import build_document
from Code_2.functions.embedding.fields import load_rules
from Code_2.functions.embedding.store import ChromaStore
from Code_2.functions.qa.pipeline import evidence_rows, build_filters
from Code_2.tests.test_indexing import FakeProvider
from Code_2.tests.test_preparation import fixture


def parent_fixture():
    one = '<table><tr><th>114及113年度</th></tr><tr><td>123</td></tr></table>\n'
    two = '<!-- Page: 2330_2025_P42 -->\n<table><tr><td>456</td></tr></table>\n'
    doc = fixture(one, 'table')
    doc['schema_version'] = 'financial-chunks/2.0'
    doc['rule_version'] = 'heading-content-chunks/2.0'
    first = doc['chunks'][0]
    pid = doc['doc_id'] + '__t00001'
    first.update(years=[2024, 2025], table_context='現金及約當現金', parent_id=pid, part_index=1,
                 appendix_id='附表一', year_sources=[])
    first['source_spans'] = [{'start': 0, 'end': len(one), 'pages': [41]}]
    second = deepcopy(first)
    second.update(chunk_id=doc['doc_id'] + '__c00002', content=two, page=[42], part_index=2,
                  source_spans=[{'start': len(one), 'end': len(one+two), 'pages': [42]}])
    parent = deepcopy(first)
    parent.update(chunk_id=pid, parent_id=None, part_index=None, content=one+two, page=[41, 42],
                  source_spans=[{'start': 0, 'end': len(one+two), 'pages': [41, 42]}])
    doc['chunks'].append(second)
    doc['parents'] = [parent]
    return doc


class ParentIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = prepare_document(parent_fixture(), input_sha256='a'*64)
        self.rules = load_rules(Path(__file__).resolve().parents[1] / 'config' / 'embedding_fields.txt')

    def factory(self, signature):
        self.store = ChromaStore(self.root / 'db', signature=signature)
        self.addCleanup(self.store.close)
        return self.store

    def build(self):
        return build_document(self.doc, prepared_sha256='b'*64, rules=self.rules, provider=FakeProvider(),
                              batch_size=2, store_factory=self.factory)

    def test_year_contains_and_full_parent_deduplicated_without_output(self):
        validate_prepared(self.doc)
        self.assertIn('表格前置標題：現金及約當現金', self.doc['chunks'][0]['embedding_text'])
        self.assertNotIn('report_year', self.doc['chunks'][0]['metadata'])
        self.assertEqual(self.build()['written'], 2)
        where = build_filters(self.store.signature, stock_code='2330', report_year=2024)
        rows = self.store.search([0.6, 0.8], n_results=5, where=where)
        self.assertEqual(len(rows), 2)
        evidence = evidence_rows(rows)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(len(evidence[0]['matched_chunk_ids']), 2)
        self.assertEqual(evidence[0]['page'], [41, 42])
        self.assertIn('123', evidence[0]['text'])
        self.assertIn('456', evidence[0]['text'])
        self.assertEqual(evidence[0]['chunk_id'], self.doc['parents'][0]['chunk_id'])
        self.assertEqual(self.store.search([0.6, 0.8], where={'years': {'$contains': 2023}}), [])
        with closing(sqlite3.connect(self.store.registry)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM table_parents').fetchone()[0], 1)

    def test_missing_parent_rejected_in_prepare_search_and_repeat(self):
        invalid = deepcopy(self.doc)
        invalid['parents'] = []
        with self.assertRaises(ValueError):
            validate_prepared(invalid)
        self.build()
        with closing(sqlite3.connect(self.store.registry)) as conn:
            conn.execute('DELETE FROM table_parents')
            conn.commit()
            digest = conn.execute('SELECT content_hash FROM documents').fetchone()[0]
        with self.assertRaisesRegex(ValueError, '父[表項]'):
            self.store.search([0.6, 0.8])
        with self.assertRaisesRegex(ValueError, '父[表項]'):
            self.store.existing(self.doc['doc_id'], digest, [c['chunk_id'] for c in self.doc['chunks']])

    def test_failed_vector_write_rolls_back_parent_and_child(self):
        def factory(signature):
            store = self.factory(signature)
            store.collection.add = lambda **kwargs: (_ for _ in ()).throw(RuntimeError('模擬寫入失敗'))
            return store
        with self.assertRaises(RuntimeError):
            build_document(self.doc, prepared_sha256='b'*64, rules=self.rules, provider=FakeProvider(),
                           batch_size=2, store_factory=factory)
        with closing(sqlite3.connect(self.store.registry)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM table_parents').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0], 0)
        self.assertEqual(self.store.collection.count(), 0)


if __name__ == '__main__':
    unittest.main()
