"""新兩模式的實際暫存Chroma隔離及直接父項回傳；僅假向量。"""
import sys
import tempfile
import unittest
import gc
import time
import sqlite3
from contextlib import contextmanager,closing
from pathlib import Path
from Code.tests.test_hierarchical_modes import run
from Code_2.functions.embedding.prepare import prepare_document
from Code_2.functions.embedding.fields import load_rules
from Code_2.functions.embedding.indexing import build_document
from Code_2.functions.embedding.store import ChromaStore
from Code_2.functions.qa.pipeline import evidence_rows
from Code_2.tests.test_indexing import FakeProvider


@contextmanager
def temporary_store():
    folder = tempfile.TemporaryDirectory()
    try:
        yield folder.name
    finally:
        # Chroma/Rust在Windows的背景檔案釋放可能晚於close；不忽略清理失敗。
        for attempt in range(21):
            gc.collect()
            try:
                folder.cleanup()
                break
            except PermissionError:
                if attempt == 20:
                    raise
                time.sleep(.05)


class HierarchicalIndexTests(unittest.TestCase):
    def test_both_parent_kinds_persist_and_missing_heading_prevents_repeat(self):
        doc=run('## (一)甲\n'+'甲'*1000+'\n## (二)乙\n乙文。\n','parent_child').document
        prepared=prepare_document(doc,input_sha256='a'*64)
        rules=load_rules(Path(__file__).resolve().parents[1]/'config/embedding_fields.txt')
        with temporary_store() as folder:
            stores=[]
            def factory(signature):
                store=ChromaStore(Path(folder),signature=signature)
                stores.append(store)
                return store
            provider=FakeProvider()
            try:
                result=build_document(prepared,prepared_sha256='b'*64,rules=rules,provider=provider,
                                      batch_size=10,store_factory=factory)
                self.assertEqual(result['status'],'indexed')
                found=stores[0].search([.6,.8],n_results=20)
                self.assertEqual(len(found),3)  # 只建立搜尋子項向量，不包括任何父項。
                self.assertTrue(all('original_heading_parent' in row['payload'] for row in found))
                evidence=evidence_rows(found,include_heading_parent=True)
                self.assertEqual(sum(e['parent_relation']=='heading' for e in evidence),1)
                self.assertEqual(sum(e['parent_relation']=='content' for e in evidence),1)
                calls=provider.calls
                again=build_document(prepared,prepared_sha256='b'*64,rules=rules,provider=provider,
                                     batch_size=10,store_factory=factory)
                self.assertEqual(again['status'],'already_indexed')
                self.assertEqual(provider.calls,calls)
                heading=next(p for p in doc['parents'] if p['node_type']=='heading_parent')
                with closing(sqlite3.connect(stores[0].registry)) as conn:
                    conn.execute('DELETE FROM table_parents WHERE parent_id=?',(heading['chunk_id'],))
                    conn.commit()
                with self.assertRaisesRegex(ValueError,'父'):
                    build_document(prepared,prepared_sha256='b'*64,rules=rules,provider=provider,
                                   batch_size=10,store_factory=factory)
                self.assertEqual(provider.calls,calls)
            finally:
                for store in stores:
                    store.close()

    def test_new_modes_and_parameters_get_separate_collections(self):
        with temporary_store() as folder:
            signatures = []
            rules = load_rules(Path(__file__).resolve().parents[1] / 'config/embedding_fields.txt')
            for mode, target in [('original',300), ('parent_child',300), ('parent_child',450)]:
                doc = run('甲'*400+'\n\n'+'乙'*400+'\n', mode, child_target=target, explicit_content_boundaries=True).document
                prepared = prepare_document(doc, input_sha256='a'*64)
                opened = []
                def factory(signature):
                    store = ChromaStore(Path(folder), signature=signature)
                    opened.append(store)
                    return store
                try:
                    outcome = build_document(prepared, prepared_sha256='b'*64, rules=rules,
                        provider=FakeProvider(), batch_size=2, store_factory=factory)
                    self.assertEqual(outcome['status'], 'indexed')
                    signatures.append(outcome['collection'])
                    rows = opened[0].search([.6,.8], n_results=20)
                    evidence = evidence_rows(rows)
                    if mode == 'parent_child':
                        # 5.3先合併同路徑content，超限切子項後必回完整內文父項。
                        self.assertEqual(len(evidence),1)
                        self.assertEqual(evidence[0]['parent_relation'],'content')
                        self.assertIn('甲'*400,evidence[0]['text'])
                        self.assertIn('乙'*400,evidence[0]['text'])
                        expanded=evidence_rows(rows,include_heading_parent=True)
                        self.assertEqual(expanded,evidence)
                        self.assertEqual(evidence[0]['chunk_id'],doc['parents'][0]['chunk_id'])
                    else:
                        self.assertEqual(len(evidence),1)
                        self.assertIn('甲'*400+'\n'+'乙'*400,evidence[0]['text'])
                        self.assertTrue(all(e['parent_id'] is None for e in evidence))
                finally:
                    for store in opened:
                        store.close()
            self.assertEqual(len(set(signatures)), 3)


if __name__ == '__main__':
    unittest.main()
