"""假向量與暫存題庫／報告；不呼叫外部模型、不寫既有實驗資料。"""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
from Code_2.config.embedding import Settings
from Code_2.config.qa import QASettings
from Code_2.functions.qa.question_bank import query_vector
from Code_2.functions.qa.pipeline import ask
from Code_2.functions.experiments.export_output import reserve_qa_run, export_qa_run
from Code_2.functions.web.service import report_path, reports
from Code_2.tests.test_qa import PROFILE, INDEX, raw_row
from Code_2.tests.test_qa_export import result


class QuestionBankTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(project_root=Path(self.tmp.name))

    def test_persistent_exact_match_model_isolation_and_zero_new_usage(self):
        generate = Mock(return_value=([1., 0.], {'total_tokens': 12}))
        first = query_vector(self.settings, '問題', PROFILE, generate)
        second = query_vector(self.settings, '問題', PROFILE, generate)
        self.assertFalse(first[2]['hit'])
        self.assertTrue(second[2]['hit'])
        self.assertEqual(second[1]['total_tokens'], 0)
        self.assertEqual(second[0], first[0])
        generate.assert_called_once()
        for question, profile in [('問題 ', PROFILE), ('問題', {**PROFILE, 'revision': 'different'}),
                                  ('問題', {**PROFILE, 'backend': 'voyage'})]:
            self.assertFalse(query_vector(self.settings, question, profile, generate)[2]['hit'])

    def test_invalid_or_failed_vectors_not_saved(self):
        for generate in (Mock(side_effect=RuntimeError('失敗')), Mock(return_value=([0., 0.], {}))):
            with self.assertRaises((RuntimeError, ValueError)):
                query_vector(self.settings, '錯誤題目', PROFILE, generate)
        self.assertFalse(query_vector(self.settings, '錯誤題目', PROFILE, lambda: ([1.,0.],{}))[2]['hit'])

    def test_pipeline_shares_across_indexes_but_not_results(self):
        provider = Mock(profile=PROFILE)
        provider.embed.return_value = [[1.,0.]]
        store = Mock(collection_name='test')
        store.search.return_value = [raw_row()]
        for i in range(2):
            index = deepcopy(INDEX)
            index['signature']['experiment'] = {'name': str(i)}
            output = ask('相同問題', self.settings, index=index, mode='retrieve',
                         provider_factory=lambda *a: provider, store_factory=lambda *a, **k: store)
            self.assertEqual(output['status'], 'retrieved')
            self.assertEqual(output['query_embedding']['cache']['hit'], bool(i))
        provider.embed.assert_called_once()
        self.assertEqual(store.search.call_count, 2)

    def test_select_children_before_parent_dedup_no_refill_original_no_heading(self):
        from Code_2.tests.test_table_parents import parent_fixture
        doc = parent_fixture()
        rows=[]
        for i, child in enumerate(doc['chunks']):
            row=raw_row();cid=child['chunk_id']
            row.update(chunk_id=cid, distance=i/10)
            row['metadata'].update(_sys_chunk_id=cid,_sys_doc_id=child['doc_id'])
            row['payload'].update(original_chunk=child,original_parent=doc['parents'][0])
            rows.append(row)
        last=deepcopy(rows[0]);child=deepcopy(last['payload']['original_chunk'])
        child.update(chunk_id=doc['doc_id']+'__c99999',parent_id=None)
        last.update(chunk_id=child['chunk_id']);last['metadata']['_sys_chunk_id']=child['chunk_id']
        last['payload']['original_chunk']=child
        rows.append(last)
        provider=Mock(profile=PROFILE);provider.embed.return_value=[[1.,0.]]
        store=Mock(collection_name='test');store.search.return_value=rows
        index=deepcopy(INDEX);index['signature']['source_chunk_rule']='content-end-original/1.0'
        output=ask('父表測試',self.settings,index=index,mode='retrieve',qa=QASettings(evidence_k=2,include_heading_parent=True),
                   provider_factory=lambda *a:provider,store_factory=lambda *a,**k:store)
        self.assertEqual(output['status'],'retrieved',output)
        self.assertEqual(len(output['selected_child_ids']),2)
        self.assertEqual(len(output['evidence']),1)
        self.assertEqual(len(output['retrieved_evidence']),2)
        self.assertEqual(len(output['evidence'][0]['matched_chunk_ids']),2)

    def test_new_report_roots_per_question_and_legacy_history(self):
        roots=[]
        for mode, role in [('retrieve','embedding'),('rerank','rerank'),('answer','answer')]:
            paths=reserve_qa_run(self.settings, mode=mode)
            self.assertEqual(paths['json'].parent.parent.name,'reponse_'+role)
            export_qa_run(self.settings,paths,result())
            roots.append(paths['json'].parent)
            self.assertTrue((roots[-1]/'ID_001.md').is_file())
            question=json.loads((roots[-1]/'ID_001.json').read_text(encoding='utf-8'))
            self.assertNotIn('reference',question)
            self.assertEqual(question['evidence'][0]['text'],result()['evidence'][0]['text'])
            self.assertEqual(report_path(self.settings,roots[-1].name,'result.json'),paths['json'])
        old=reserve_qa_run(self.settings)
        export_qa_run(self.settings,old,result())
        self.assertEqual(len(reports(self.settings,Mock(history_limit=50))),4)

    def test_named_rerank_folders_remain_readable(self):
        for name in ('BGE 父子250', 'BGE 原始', 'Voyage 父子250', 'Voyage 原始'):
            paths=reserve_qa_run(self.settings,mode='rerank')
            export_qa_run(self.settings,paths,result())
            target=paths['json'].parent.with_name(name)
            paths['json'].parent.rename(target)
            self.assertEqual(report_path(self.settings,name,'result.json'),target/'result.json')
        self.assertEqual(len(reports(self.settings,Mock(history_limit=50))),4)
        for invalid in ('../BGE 原始', 'BGE 原始/../', 'BGE 未知', 'Voyage 父子700'):
            with self.assertRaises(ValueError):
                report_path(self.settings,invalid,'result.json')

    def test_disable_export_still_allows_question_bank(self):
        from dataclasses import replace
        settings=replace(self.settings,export_enabled=False)
        self.assertIsNone(reserve_qa_run(settings,mode='retrieve'))
        query_vector(settings,'題庫非實驗輸出',PROFILE,lambda:([1.,0.],{}))
        self.assertTrue(settings.question_bank_path.is_file())
        self.assertFalse((settings.project_root/'Output').exists())
