"""實際暫存Chroma、假向量：驗證命名索引隔離及重複匯入，無模型／API。"""
import unittest,json
from copy import deepcopy
from Code_2.tests import test_indexing as fixtures
from Code.functions.embedding.index_target import bind_signature, resolve_target, validate_choice


class NamedIndexTests(unittest.TestCase):
    setUp=fixtures.IndexTests.setUp
    cleanup_temp=fixtures.IndexTests.cleanup_temp
    factory=fixtures.IndexTests.factory
    build=fixtures.IndexTests.build

    def test_same_settings_and_name_can_create_isolated_experiments(self):
        a=resolve_target(self.settings,'bge',mode='new',name='父子250測試')
        b=resolve_target(self.settings,'bge',mode='new',name='父子250測試')
        first=self.build(index_target=a)
        first_store=self.store
        second=self.build(index_target=b)
        self.assertNotEqual(first['collection'],second['collection'])
        self.assertEqual(first['display_name'],'父子250測試')
        self.assertEqual(len(first_store.search([.6,.8],n_results=5)),len(self.store.search([.6,.8],n_results=5)))
        self.assertEqual(first_store.collection.count(),self.store.collection.count())

    def test_add_same_document_to_existing_skips_embedding(self):
        self.build(index_target=resolve_target(self.settings,'bge',mode='new',name='測試A'))
        signature=json.loads(json.dumps(self.store.signature))
        provider=fixtures.FakeProvider()
        result=self.build(provider=provider,index_target={'signature':signature})
        self.assertEqual(result['status'],'already_indexed')
        self.assertEqual(provider.calls,0)

    def test_incompatible_existing_index_rejected_before_embedding(self):
        self.build(index_target=resolve_target(self.settings,'bge',mode='new',name='測試A'))
        signature=deepcopy(self.store.signature)
        signature['model']['model']='another-model'
        provider=fixtures.FakeProvider()
        with self.assertRaisesRegex(ValueError,'不同'):
            self.build(provider=provider,index_target={'signature':signature})
        self.assertEqual(provider.calls,0)

    def test_updated_document_still_cannot_overwrite_old_vectors(self):
        self.build(index_target=resolve_target(self.settings,'bge',mode='new',name='測試A'))
        store=self.store;signature=deepcopy(store.signature);count=store.collection.count()
        with self.assertRaisesRegex(ValueError,'不同版本'):
            self.build(digest='c'*64,index_target={'signature':signature})
        self.assertEqual(store.collection.count(),count)

    def test_catalog_name_and_existing_selection_round_trip(self):
        from Code.functions.embedding.store import ChromaStore
        from Code.functions.embedding.catalog import list_indexes
        from Code.functions.embedding.indexing import build_document
        provider=fixtures.FakeProvider();provider.profile={**provider.profile,'backend':'bge'}
        def factory(signature):
            store=ChromaStore(self.settings.vector_root/'bge',signature=signature)
            self.addCleanup(store.close)
            return store
        target=resolve_target(self.settings,'bge',mode='new',name='清單測試')
        first=build_document(self.doc,prepared_sha256='b'*64,rules=self.rules,provider=provider,
            batch_size=1,store_factory=factory,index_target=target)
        indexes=list_indexes(self.settings,'bge')
        self.assertEqual(indexes[0]['display_name'],'清單測試')
        existing=resolve_target(self.settings,'bge',mode='existing',collection=first['collection'])
        repeated=build_document(self.doc,prepared_sha256='b'*64,rules=self.rules,provider=provider,
            batch_size=1,store_factory=factory,index_target=existing)
        self.assertEqual(repeated['status'],'already_indexed')

    def test_legacy_signature_and_invalid_names(self):
        signature={'model':{'model':'old'}}
        self.assertEqual(bind_signature(signature,None),signature)
        for name in ['', ' '*5, 'a'*81, 'bad\nname']:
            with self.subTest(name=name),self.assertRaises(ValueError):validate_choice('new',name)
        with self.assertRaises(ValueError):validate_choice('existing',collection='../unsafe')


if __name__=='__main__':unittest.main()
