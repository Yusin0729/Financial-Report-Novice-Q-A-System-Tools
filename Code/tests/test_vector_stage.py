"""第五階段與文件管理：真實暫存Chroma、合成向量，不使用金鑰或既有索引。"""
import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from Code.config.embedding import Settings
from Code.functions.embedding.direct import build_files
from Code.functions.embedding.catalog import list_indexes
from Code.functions.embedding.management import open_index, documents, snapshot, delete_documents, browse_chunks
from Code.vector import dispatch
from Code_2.tests.test_preparation import fixture


class Provider:
    limit = 8192
    def __init__(self, backend):
        self.profile = {'backend': backend, 'model': 'test-only', 'dimension': 2}
        self.calls = 0
    def count_tokens(self, texts): return [10] * len(texts)
    def embed(self, texts, *, batch_size):
        self.calls += 1
        return [[.6, .8] for _ in texts]


class VectorStageTests(unittest.TestCase):
    def test_context_modes_create_separate_indexes_and_cannot_mix(self):
        first=self.build()
        old=list_indexes(self.settings)[0]['signature']
        from Code.tests.test_hierarchical_modes import run
        doc=run('內文。\n',text_embedding_mode='body',table_embedding_mode='description').document
        self.source=self.source.with_name('2025_2330_chunk_text-body_table-description.json')
        self.source.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
        second=self.build()
        self.assertEqual(second['status'],'indexed')
        self.assertNotEqual(first['collection'],second['collection'])
        self.assertEqual(len(list_indexes(self.settings)),2)
        calls=self.providers['bge'].calls
        self.assertEqual(self.build(index_target={'signature':old})['status'],'failed')
        self.assertEqual(self.providers['bge'].calls,calls)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='第五階段 測試 ')
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(project_root=Path(self.tmp.name))
        self.settings.fields_file.parent.mkdir(parents=True)
        self.settings.fields_file.write_bytes(Settings().fields_file.read_bytes())
        self.source = self.settings.input_dir / 'Financial_chunk_20261025_12-00-00' / '2025_2330_chunk.json'
        self.source.parent.mkdir(parents=True)
        self.source.write_text(json.dumps(fixture(), ensure_ascii=False), encoding='utf-8')
        self.providers = {}
    def provider(self, backend, settings):
        return self.providers.setdefault(backend, Provider(backend))
    def build(self, **kwargs):
        return build_files([self.source], self.settings, backend='bge', provider_factory=self.provider, **kwargs)[0]
    def store(self):
        index = list_indexes(self.settings)[0]
        store = open_index(self.settings, index['backend'], index['collection'])
        self.addCleanup(store.close)
        return store

    def test_direct_memory_repeat_and_no_prepared_output(self):
        raw = self.source.read_bytes()
        first = self.build()
        self.assertEqual(first['status'], 'indexed')
        self.assertEqual(self.build()['status'], 'already_indexed')
        self.assertEqual(self.providers['bge'].calls, 1)
        self.assertFalse(self.settings.output_dir.exists())
        self.assertEqual(self.source.read_bytes(), raw)
        store = self.store()
        self.assertEqual(len(store.search([.6,.8])), 1)
        content = browse_chunks(store, fixture()['doc_id'])
        self.assertEqual(content['chunks'][0]['original_chunk']['content'], fixture()['chunks'][0]['content'])

    def test_filters_preview_delete_and_reimport(self):
        self.build()
        store = self.store()
        self.assertEqual(len(documents(store, stock_code='2330', year=2025, doc_id='2025Q4')), 1)
        self.assertEqual(documents(store, year=2024), [])
        identity = fixture()['doc_id']
        preview = snapshot(store, [identity])
        with self.assertRaises(ValueError): delete_documents(store, [identity], 'stale')
        self.assertEqual(len(store.search([.6,.8])), 1)
        self.assertEqual(delete_documents(store, [identity], preview['token'])['deleted'], [identity])
        self.assertEqual(documents(store), [])
        self.assertEqual(store.search([.6,.8]), [])
        self.assertEqual(self.build()['status'], 'indexed')

    def test_delete_failure_gates_query_and_can_retry(self):
        self.build()
        store = self.store()
        ids = [fixture()['doc_id']]
        preview = snapshot(store, ids)
        with patch.object(store.collection, 'delete', side_effect=RuntimeError('simulated')):
            with self.assertRaises(RuntimeError): delete_documents(store, ids, preview['token'])
        self.assertEqual(store.search([.6,.8]), [])
        self.assertEqual(documents(store)[0]['status'], 'deletion_pending')
        self.assertEqual(self.build()['status'], 'failed')
        preview = snapshot(store, ids)
        delete_documents(store, ids, preview['token'])
        self.assertEqual(documents(store), [])

    def test_check_only_and_over_limit_do_not_write(self):
        self.assertEqual(self.build(check_only=True)['status'], 'checked')
        self.assertFalse(self.settings.vector_root.exists())
        self.providers['bge'].limit = 5
        self.assertEqual(self.build()['status'], 'blocked_token_limit')
        self.assertEqual(list_indexes(self.settings), [])

    def test_mode_model_and_parameters_isolation_delete_scope(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_hierarchical_modes import run
        collections = []
        from dataclasses import replace
        settings = replace(self.settings, allow_voyage_api=True)
        for backend, mode, target in [('bge','original',300),('bge','parent_child',300),
                                      ('bge','parent_child',450),('voyage','original',300)]:
            doc = run('甲'*400+'\n\n'+'乙'*400+'\n', mode, child_target=target).document
            source = self.source.parent / mode / f'{doc["doc_id"][:4]}_2330_chunk_text-full_table-full.json'
            source.parent.mkdir(exist_ok=True)
            source.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
            outcome = build_files([source], settings, backend=backend, provider_factory=self.provider)[0]
            self.assertEqual(outcome['status'], 'indexed')
            collections.append((backend,outcome['collection']))
        self.assertEqual(len(set(collections)), 4)
        backend, name = collections[1]
        store = open_index(settings, backend, name)
        try:
            ids = [documents(store)[0]['doc_id']]
            preview = snapshot(store, ids)
            delete_documents(store, ids, preview['token'])
            with closing(sqlite3.connect(store.registry)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM table_parents WHERE collection=?',(name,)).fetchone()[0],0)
        finally:
            store.close()
        self.assertEqual(len(list_indexes(settings)), 3)

    def test_threshold_suffix_builds_separate_collections_and_rejects_mismatch(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from test_hierarchical_modes import run
        sources=[]
        folder=self.source.parent/'parent_child'
        folder.mkdir()
        for limit in (700,1000):
            doc=run('甲'*1000+'\n','parent_child',recursive_threshold=limit).document
            source=folder/f'2025_2330_chunk_{limit}_text-full_table-full.json'
            source.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
            sources.append(source)
        results=build_files(sources,self.settings,backend='bge',provider_factory=self.provider)
        self.assertEqual([r['status'] for r in results],['indexed','indexed'])
        self.assertEqual(len({r['collection'] for r in results}),2)
        indexes=list_indexes(self.settings)
        self.assertEqual({i['signature']['chunking']['recursive_threshold'] for i in indexes},{700,1000})
        for index in indexes:
            store=open_index(self.settings,'bge',index['collection'])
            try:
                expected=2 if index['signature']['chunking']['recursive_threshold']==700 else 1
                self.assertEqual(len(store.search([.6,.8])),expected)
            finally:
                store.close()
        bad=folder/'2025_2330_chunk_900_text-full_table-full.json'
        bad.write_bytes(sources[0].read_bytes())
        calls=self.providers['bge'].calls
        result=build_files([bad],self.settings,backend='bge',provider_factory=self.provider)[0]
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['stage'],'source_validation')
        self.assertIn('字數後綴',result['error'])
        self.assertEqual(self.providers['bge'].calls,calls)

    def test_invalid_source_and_voyage_require_opt_in_before_provider(self):
        with self.assertRaises(ValueError):
            build_files([self.source], self.settings, backend='voyage', provider_factory=self.provider)
        with self.assertRaises(ValueError):
            dispatch({'action':'build', 'ids':['../outside.json'], 'backend':'bge'}, self.settings, lambda e:None)
        self.assertFalse(self.providers)
        self.assertFalse(self.settings.vector_root.exists())

    def test_bad_file_reports_its_stage_and_other_file_continues(self):
        bad = self.source.with_name('2025_2303_chunk.json')
        bad.write_text('{invalid', encoding='utf-8')
        events = []
        rows = build_files([bad, self.source], self.settings, backend='bge',
                           provider_factory=self.provider, progress=events.append)
        self.assertEqual([r['status'] for r in rows], ['failed', 'indexed'])
        self.assertEqual(rows[0]['stage'], 'source_validation')
        results = [e['result'] for e in events if 'result' in e]
        self.assertEqual(len(results), 2)
        self.assertEqual([r['elapsed_seconds'] for r in results], [r['elapsed_seconds'] for r in rows])
        for item in results:
            self.assertEqual(item['runtime_config'], {'cpu_threads': self.settings.cpu_threads,
                'batch_size': self.settings.bge_batch_size, 'batch_unit': 'chunk'})
        self.assertEqual(self.providers['bge'].calls, 1)

    def test_worker_protocol_rejects_escape_without_models(self):
        import subprocess, sys
        root = Settings().project_root
        result = subprocess.run([sys.executable, '-X', 'utf8', str(root/'Code/vector.py'), '--rpc'],
            input=json.dumps({'action':'build','ids':['../outside.json'],'backend':'bge'}),
            text=True, encoding='utf-8', capture_output=True, cwd=root, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['state'], 'failed')
        self.assertNotIn('Traceback', result.stdout)


if __name__ == '__main__': unittest.main()
