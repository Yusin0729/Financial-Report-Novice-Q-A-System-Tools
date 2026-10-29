"""Offline fake tokenizer/model tests; never download weights or call external APIs."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from Code_2.config.embedding import Settings
from Code_2.config.qa import QASettings
from Code_2.functions.qa.bge_reranker import BgeReranker, BgeRerankError
from Code_2.functions.qa.rerankers import LOCAL_BGE_PROFILE, resolve_rerank_profile, create_reranker
from Code_2.functions.qa.pipeline import ask
from Code_2.functions.web.service import validate_task
from Code_2.tests.test_qa import PROFILE, INDEX, raw_row


class Tokenizer:
    model_max_length=8192
    def __init__(self):self.calls=[]
    def __call__(self,q,text,**kwargs):
        self.calls.append((q,text,kwargs))
        return {'input_ids':[int(text) if text.isdigit() else 0]*(len(text)+4),
                'attention_mask':[1]*(len(text)+4)}
    def pad(self,items,**kwargs):
        import torch
        return {'input_ids':torch.tensor([[v['input_ids'][0]] for v in items])}


class Model:
    def __init__(self):self.calls=0
    def __call__(self,**batch):
        self.calls+=1
        return SimpleNamespace(logits=batch['input_ids'].float())


class BgeRerankerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.settings=Settings(project_root=Path(self.tmp.name))
        self.qa=replace(QASettings(),evidence_k=2,rerank_profile=LOCAL_BGE_PROFILE)
        self.tokenizer=Tokenizer();self.model=Model()
        self.reranker=BgeReranker(self.settings,self.qa,tokenizer=self.tokenizer,model=self.model)
        self.evidence=[{'id':f'S{i}','chunk_id':f'c{i}','text':text,'page':[i+1]} for i,text in enumerate(['1','3','3'])]

    def test_full_pairs_order_ties_topk_metadata_and_zero_api_usage(self):
        selected,usage=self.reranker.rerank('question',self.evidence)
        self.assertEqual([s['chunk_id'] for s in selected],['c1','c2'])
        self.assertEqual([s['rerank_rank'] for s in selected],[1,2])
        self.assertEqual(self.model.calls,3)
        self.assertTrue(all(c[2]['truncation'] is False for c in self.tokenizer.calls))
        self.assertTrue(all(0<=s['rerank_score']<=1 for s in selected))
        self.assertFalse(usage['api_called']);self.assertEqual(usage['total_tokens'],0)
        self.assertEqual(usage['local_input_tokens'],15)
        self.assertNotIn('rerank_rank',self.evidence[1])

    def test_overlength_fails_before_any_inference_and_never_truncates(self):
        with self.assertRaisesRegex(BgeRerankError,'8192.*未截斷'):
            self.reranker.rerank('question',[self.evidence[0],{'text':'x'*8193}])
        self.assertEqual(self.model.calls,0)

    def test_nonfinite_model_output_rejected(self):
        import torch
        self.reranker.model=lambda **kwargs:SimpleNamespace(logits=torch.tensor([float('nan')]))
        with self.assertRaisesRegex(BgeRerankError,'非有限'):
            self.reranker.rerank('question',self.evidence)

    def test_local_profile_and_factory_do_not_resolve_any_api_key(self):
        with patch('Code.functions.embedding.api_settings.resolve_profile',side_effect=AssertionError('no keys')):
            profile,key=resolve_rerank_profile(self.settings.project_root,LOCAL_BGE_PROFILE)
            reranker,qa=create_reranker(self.settings,self.qa)
        self.assertEqual(profile['provider'],'bge');self.assertIsNone(key)
        self.assertIsInstance(reranker,BgeReranker);self.assertEqual(qa.rerank_provider,'bge')

    def test_web_accepts_bge_profile_without_credentials(self):
        with patch('Code.functions.embedding.api_settings.resolve_profile',side_effect=AssertionError('no keys')):
            task=validate_task({'action':'query','question':'營收','mode':'rerank','backend':'bge',
                'collection':'financial_'+'a'*24,'retrieve_k':50,'evidence_k':10,
                'rerank_profile':LOCAL_BGE_PROFILE,'export_enabled':False},self.settings)
        self.assertEqual(task['rerank_profile'],LOCAL_BGE_PROFILE)

    def test_query_uses_local_reranker_without_voyage_and_records_provider(self):
        provider=Mock(profile=PROFILE);provider.embed.return_value=[[1.,0.]]
        store=Mock(collection_name=INDEX['collection']);store.search.return_value=[raw_row()]
        local=Mock();local.rerank.side_effect=lambda q,e:([{**e[0],'rerank_rank':1,'rerank_score':.8}],{'provider':'bge','model':'BAAI/bge-reranker-v2-m3','total_tokens':0,'api_called':False})
        with patch('Code_2.functions.qa.bge_reranker.BgeReranker',return_value=local),patch('Code_2.functions.qa.pipeline.service_key',side_effect=AssertionError('no keys')):
            result=ask('營收',self.settings,mode='rerank',qa=self.qa,index=INDEX,
                provider_factory=lambda *a:provider,store_factory=lambda *a,**kw:store)
        self.assertEqual(result['status'],'reranked',result)
        self.assertEqual(result['rerank_provider'],'bge')
        self.assertEqual(result['rerank_model'],'BAAI/bge-reranker-v2-m3')
        local.rerank.assert_called_once()

    def test_saved_report_local_validation_factory_and_export(self):
        # Reuse the established temporary report fixture, not any user report.
        from Code_2.tests.test_saved_rerank import SavedRerankTests
        from Code_2.functions.experiments.saved_rerank import validate_task,run
        fixture=SavedRerankTests('test_reuse_exact_candidates_without_embedding_and_preserve_source')
        fixture.setUp()
        try:
            task=validate_task({'action':'rerank-report','source_run':fixture.name,'ids':['1'],
                'rerank_profile':LOCAL_BGE_PROFILE,'evidence_k':1,'generate_charts':True},fixture.settings)
            local=Mock();local.rerank.side_effect=lambda q,e:([{**e[0],'rerank_rank':1,'rerank_score':.9}],{'provider':'bge','total_tokens':0,'local_input_tokens':50,'api_called':False})
            with patch('Code_2.functions.qa.bge_reranker.BgeReranker',return_value=local):
                output=run(task,fixture.settings)['evaluation']
            self.assertEqual(output['status'],'completed',output)
            self.assertEqual(output['rows'][0]['query']['rerank_provider'],'bge')
            self.assertEqual(output['rows'][0]['query']['rerank']['total_tokens'],0)
            self.assertEqual(output['settings']['rerank_provider'],'bge')
            self.assertTrue((Path(output['output_dir'])/'results.xlsx').is_file())
        finally:fixture.tearDown()

    def test_multiple_questions_share_one_loaded_model(self):
        from Code_2.functions.qa.bge_reranker import _model_from_cache
        _model_from_cache.cache_clear()
        try:
            fake=Mock();fake.to.return_value=fake;fake.eval.return_value=fake
            with patch('transformers.AutoModelForSequenceClassification.from_pretrained',return_value=fake) as loader:
                a=BgeReranker(self.settings,self.qa);b=BgeReranker(self.settings,self.qa)
                self.assertIs(a._model(),b._model())
                loader.assert_called_once()
        finally:_model_from_cache.cache_clear()

    def test_cli_passes_local_profile_without_running_models(self):
        from Code_2.main import main
        with patch('Code_2.main.run_question',return_value={'status':'reranked','evidence':[]}) as run,patch('Code_2.main.show_question_result'):
            self.assertEqual(main(['--ask','營收','--qa-mode','rerank','--rerank-profile',LOCAL_BGE_PROFILE]),0)
        self.assertEqual(run.call_args.kwargs['qa'].rerank_profile,LOCAL_BGE_PROFILE)

    def test_local_failure_message_is_preserved_for_user(self):
        provider=Mock(profile=PROFILE);provider.embed.return_value=[[1.,0.]]
        store=Mock(collection_name=INDEX['collection']);store.search.return_value=[raw_row()]
        local=Mock();local.rerank.side_effect=BgeRerankError('BGE重排序第1個候選含9000 tokens，超過8192上限；未截斷、未改用其他模型')
        with patch('Code_2.functions.qa.bge_reranker.BgeReranker',return_value=local):
            output=ask('營收',self.settings,mode='rerank',qa=self.qa,index=INDEX,
                provider_factory=lambda *a:provider,store_factory=lambda *a,**kw:store)
        self.assertEqual(output['stage'],'rerank')
        self.assertIn('8192',output['error'])
