"""整集合移除：暫存真實Chroma／假向量，驗證中斷重試與隔離。"""
import json
import sqlite3
import tempfile
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from Code.config.embedding import Settings
from Code.functions.embedding.direct import build_files
from Code.functions.embedding.catalog import list_indexes
from Code.functions.embedding.store import ChromaStore
from Code.functions.embedding.collection_management import collection_snapshot, delete_collection, _delete_native
from Code.tests.test_vector_stage import Provider
from Code_2.tests.test_preparation import fixture


class CollectionManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='collection_delete_')
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(project_root=Path(self.tmp.name))
        self.settings.fields_file.parent.mkdir(parents=True)
        self.settings.fields_file.write_bytes(Settings().fields_file.read_bytes())
        self.source = self.settings.input_dir/'Financial_chunk_20261025_12-00-00'/'2025_2330_chunk.json'
        self.source.parent.mkdir(parents=True)
        self.source.write_text(json.dumps(fixture(), ensure_ascii=False), encoding='utf-8')
        self.provider = Provider('bge')
        self.row = self.build()
        self.collection = self.row['collection']
        self.root = self.settings.vector_root/'bge'
        self.signature = list_indexes(self.settings)[0]['signature']

    def build(self):
        return build_files([self.source], self.settings, backend='bge',
                           provider_factory=lambda *args:self.provider)[0]

    def preview(self):
        return collection_snapshot(self.settings, 'bge', self.collection)

    def test_snapshot_and_delete_without_vector_get_preserve_other_collection_and_attempts(self):
        text = self.settings.fields_file.read_text(encoding='utf-8')
        self.settings.fields_file.write_text(text.replace('metadata.page = metadata','metadata.page = ignore'),encoding='utf-8')
        other = self.build()['collection']
        self.assertNotEqual(other,self.collection)
        with patch('chromadb.api.models.Collection.Collection.get', side_effect=AssertionError('must not read HNSW')):
            preview = self.preview()
            self.assertEqual(preview['count_source'],'registry')
            result = delete_collection(self.settings,'bge',self.collection,preview['token'])
        self.assertEqual(result['deleted'],[fixture()['doc_id']])
        self.assertEqual([r['collection'] for r in list_indexes(self.settings)],[other])
        with closing(sqlite3.connect(self.root/'ingestion.sqlite3')) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM attempts').fetchone()[0],2)
        index=list_indexes(self.settings)[0]
        store=ChromaStore(self.root,signature=index['signature'],create=False)
        try: self.assertEqual(len(store.collection.get(include=[])['ids']),1)
        finally: store.close()

    def test_stale_preview_does_not_remove_or_mark_collection(self):
        preview=self.preview()
        with closing(sqlite3.connect(self.root/'ingestion.sqlite3')) as c:
            c.execute('UPDATE documents SET chunk_count=2 WHERE collection=?',(self.collection,));c.commit()
        with self.assertRaisesRegex(ValueError,'預覽已過期'):
            delete_collection(self.settings,'bge',self.collection,preview['token'])
        self.assertEqual(len(list_indexes(self.settings)),1)
        self.assertFalse(self.preview()['pending'])

    def test_failure_marks_blocks_and_can_retry(self):
        store=ChromaStore(self.root,signature=self.signature,create=False)
        try:
            preview=self.preview()
            with patch('Code.functions.embedding.collection_management._delete_native',side_effect=RuntimeError('test failure')):
                with self.assertRaises(RuntimeError): delete_collection(self.settings,'bge',self.collection,preview['token'])
            self.assertEqual(list_indexes(self.settings)[0]['status'],'collection_deletion_pending')
            self.assertTrue(self.preview()['pending'])
            with self.assertRaisesRegex(ValueError,'整組移除'): store.search([.6,.8])
            with self.assertRaisesRegex(ValueError,'整組移除'): ChromaStore(self.root,signature=self.signature)
            self.assertEqual(self.build()['status'],'failed')
            self.assertEqual(self.provider.calls,1)
            delete_collection(self.settings,'bge',self.collection,self.preview()['token'])
            self.assertEqual(list_indexes(self.settings),[])
        finally: store.close()

    def test_crash_after_native_delete_before_registry_cleanup(self):
        preview=self.preview()
        def deleted_then_crash(client,name):
            _delete_native(client,name)
            raise RuntimeError('crash after native deletion')
        with patch('Code.functions.embedding.collection_management._delete_native',side_effect=deleted_then_crash):
            with self.assertRaises(RuntimeError): delete_collection(self.settings,'bge',self.collection,preview['token'])
        self.assertEqual(list_indexes(self.settings)[0]['status'],'collection_deletion_pending')
        retry=self.preview()
        self.assertTrue(retry['pending'])
        delete_collection(self.settings,'bge',self.collection,retry['token'])
        self.assertEqual(list_indexes(self.settings),[])
        self.assertEqual(self.build()['status'],'indexed')

    def test_real_corrupt_hnsw_collection_can_be_removed(self):
        settings = Settings(project_root=Path(self.tmp.name)/'中文測試')
        root=settings.vector_root/'bge'
        signature={'model':{'backend':'bge','model':'test-only','dimension':2}}
        code="""import sys,json
from pathlib import Path
from contextlib import closing
from Code.functions.embedding.store import ChromaStore
store=ChromaStore(Path(sys.argv[1]),signature=json.loads(sys.argv[2]))
store.collection.add(ids=[str(i) for i in range(1130)],embeddings=[[1.,.5] for i in range(1130)])
with closing(store.connect()) as conn:
 conn.execute('INSERT INTO documents VALUES (?,?,?,?,?,?)',(store.collection_name,'test_doc','test_hash','test_run',1130,'test_time'))
 conn.commit()
print(store.collection_name)
store.close()
"""
        result=subprocess.run([sys.executable,'-X','utf8','-c',code,str(root),json.dumps(signature)],
            capture_output=True,text=True,encoding='utf-8',cwd=Settings().project_root,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        name=result.stdout.strip().splitlines()[-1]
        store=ChromaStore(root,signature=signature,create=False)
        try:
            with self.assertRaisesRegex(Exception,'Error loading hnsw index'):
                store.collection.get(include=[])
        finally: store.close()
        preview=collection_snapshot(settings,'bge',name)
        self.assertEqual(preview['chunk_count'],1130)
        delete_collection(settings,'bge',name,preview['token'])
        self.assertEqual(list_indexes(settings),[])

    def test_invalid_scope_never_creates_empty_database(self):
        for backend,collection in [('other',self.collection),('bge','../outside')]:
            with self.assertRaises(ValueError): collection_snapshot(self.settings,backend,collection)
        with self.assertRaises(ValueError): delete_collection(self.settings,'bge',self.collection,'wrong-token')
        self.assertFalse(self.preview()['pending'])


if __name__=='__main__': unittest.main()
