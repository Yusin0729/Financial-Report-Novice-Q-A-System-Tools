"""批次命名索引：真實暫存Chroma與假向量，不呼叫模型API。"""
import json
import tempfile
import unittest
from pathlib import Path
from itertools import product
from unittest.mock import patch
from Code.vector import dispatch
from Code.config.embedding import Settings
from Code.functions.embedding.direct import build_files
from Code.functions.embedding.catalog import list_indexes
from Code.functions.embedding.job_control import create_control, request_stop
from Code.tests.test_hierarchical_modes import run
from Code.tests.test_vector_stage import Provider


class BatchIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.settings=Settings(project_root=Path(self.tmp.name))
        self.settings.fields_file.parent.mkdir(parents=True)
        self.settings.fields_file.write_bytes(Settings().fields_file.read_bytes())
        self.provider_calls=0;self.provider=Provider('bge');self.events=[]
    def factory(self,*args):
        self.provider_calls+=1
        return self.provider
    def source(self,mode='original',limit=700,text='full',table='full',batch='Financial_chunk_20261027_12-00-00',stock='2330'):
        doc=run('原文內容。\n',mode,recursive_threshold=limit,text_embedding_mode=text,table_embedding_mode=table).document
        doc=json.loads(json.dumps(doc,ensure_ascii=False).replace('2330',stock))
        suffix=f'_{limit}' if mode=='parent_child' else ''
        p=self.settings.input_dir/batch/mode/f'2025_{stock}_chunk{suffix}_text-{text}_table-{table}.json'
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
        return p
    def build(self,paths,**kwargs):
        return build_files(paths,self.settings,backend='bge',batch_prefix='批次測試',provider_factory=self.factory,progress=self.events.append,**kwargs)

    def test_27_groups_share_one_provider_and_same_group_documents_share_index(self):
        paths=[self.source(mode,limit,text,table) for mode,limit in [('original',700),('parent_child',250),('parent_child',700)]
               for text,table in product(('body','description','full'),repeat=2)]
        paths.append(self.source(text='body',table='body',stock='2303'))
        rows=self.build(paths)
        self.assertTrue(all(r['status']=='indexed' for r in rows))
        self.assertEqual(len(rows),28)
        self.assertEqual(self.provider_calls,1)
        self.assertEqual(len({r['collection'] for r in rows}),27)
        indexes=list_indexes(self.settings)
        self.assertEqual(len(indexes),27)
        self.assertEqual(sorted(len(i['doc_ids']) for i in indexes),[1]*26+[2])
        self.assertTrue(all(len(i['signature']['experiment']['name'])<=80 for i in indexes))
        self.assertEqual(len({i['signature']['experiment']['id'] for i in indexes}),27)
        self.assertEqual(len(self.events[-1]['index_groups']),27)
        self.assertTrue(all(g['status']=='completed' for g in self.events[-1]['index_groups']))

    def test_duplicate_document_in_same_group_fails_before_provider(self):
        paths=[self.source(),self.source(batch='Financial_chunk_20261027_12-00-01')]
        with self.assertRaisesRegex(ValueError,'doc_id重複'):self.build(paths)
        self.assertEqual(self.provider_calls,0)

    def test_rpc_batch_request_reaches_grouped_builder(self):
        paths=[self.source(text='body'),self.source(text='description')]
        def build(paths,settings,**kwargs):
            self.assertEqual(kwargs['batch_prefix'],'RPC前綴')
            self.assertIsNone(kwargs['index_target'])
            return build_files(paths,settings,provider_factory=self.factory,**kwargs)
        with patch('Code.vector.build_files',side_effect=build):
            result=dispatch({'action':'build','index_mode':'batch','index_name':'RPC前綴','backend':'bge',
                             'ids':[p.relative_to(self.settings.input_dir).as_posix() for p in paths]},
                            self.settings,self.events.append)
        self.assertEqual(result['state'],'completed')
        self.assertEqual(len(list_indexes(self.settings)),2)
        self.assertEqual(self.provider_calls,1)

    def test_check_only_and_invalid_source_do_not_write_indexes(self):
        valid=self.source();bad=self.source(text='body');bad.write_text('{}',encoding='utf-8')
        rows=self.build([valid,bad],check_only=True)
        self.assertEqual([r['status'] for r in rows],['checked','failed'])
        self.assertFalse(self.settings.vector_root.exists())

    def test_stop_between_groups_keeps_completed_index(self):
        paths=[self.source(text='body'),self.source(text='description')]
        ids=[p.relative_to(self.settings.input_dir).as_posix() for p in paths]
        create_control(self.settings,'a'*32,ids)
        def progress(event):
            self.events.append(event)
            if 'result' in event:request_stop(self.settings,'a'*32)
        rows=build_files(paths,self.settings,backend='bge',batch_prefix='停止測試',provider_factory=self.factory,
                         progress=progress,control_id='a'*32)
        self.assertEqual(len(rows),1)
        self.assertEqual(len(list_indexes(self.settings)),1)
        self.assertEqual([g['status'] for g in self.events[-1]['index_groups']],['completed','stopped'])
