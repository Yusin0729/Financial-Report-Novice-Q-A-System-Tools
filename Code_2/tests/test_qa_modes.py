"""三模式與Response契約；只用假模型／API，不讀實際金鑰。"""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from Code_2.config.embedding import Settings
from Code_2.config.qa import QASettings
from Code_2.functions.qa.pipeline import ask
from Code_2.functions.qa.services import VoyageReranker
from Code_2.functions.qa.run import run_question
from Code_2.functions.qa.answers import render_answer
from Code_2.main import main, interactive_qa
from Code_2.tests.test_qa import PROFILE, INDEX, raw_row, response


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(project_root=Path(self.temp.name))
        self.provider = Mock(profile=PROFILE)
        self.provider.embed.return_value = [[1., 0.]]
        self.store = Mock(collection_name='test')
        rows = []
        for i in range(50):
            row = raw_row()
            cid = f'doc__c{i + 1:05d}'
            row['chunk_id'] = row['metadata']['_sys_chunk_id'] = row['payload']['original_chunk']['chunk_id'] = cid
            rows.append(row)
        self.store.search.return_value = rows
        self.client = Mock()
        self.client.rerank.return_value = SimpleNamespace(results=[
            SimpleNamespace(index=i, relevance_score=1 - i / 100) for i in range(10)], total_tokens=9000)
        self.reranker = VoyageReranker(self.client, QASettings())
        self.answerer = Mock()
        self.answerer.answer.return_value = response(), {}
        self.services = Mock(return_value=(self.reranker, self.answerer))

    def run_mode(self, mode, **kwargs):
        return ask('原始問題', self.settings, mode=mode, index=INDEX,
                   provider_factory=lambda *a: self.provider, store_factory=lambda *a, **k: self.store,
                   service_factory=self.services, **kwargs)

    def test_retrieve_fifty_no_key_or_service_creation(self):
        with patch('Code_2.functions.qa.pipeline.service_key') as key:
            result = self.run_mode('retrieve')
        self.assertEqual(result['status'], 'retrieved')
        self.assertEqual(len(result['retrieved_evidence']), 50)
        self.assertEqual(self.store.search.call_args.kwargs['n_results'], 50)
        self.assertEqual(result['completed_stages'], ['query_embedding', 'retrieval'])
        self.services.assert_not_called()
        key.assert_not_called()
        self.client.rerank.assert_not_called()
        self.answerer.answer.assert_not_called()
        self.assertNotIn('answer', result)

    def test_rerank_fifty_to_ten_no_answer(self):
        result = self.run_mode('rerank')
        self.assertEqual(result['status'], 'reranked')
        self.assertEqual(len(result['retrieved_evidence']), 50)
        self.assertEqual(len(result['evidence']), 10)
        self.assertEqual(self.client.rerank.call_args.kwargs['top_k'], 10)
        self.assertEqual(len(self.client.rerank.call_args.kwargs['documents']), 50)
        self.assertFalse(self.client.rerank.call_args.kwargs['truncation'])
        self.answerer.answer.assert_not_called()
        self.assertNotIn('generation', result)
        self.assertEqual(result['completed_stages'], ['query_embedding', 'retrieval', 'rerank'])

    def test_full_answer_only_ten_evidence_reaches_gemini(self):
        result = self.run_mode('answer')
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(len(self.answerer.answer.call_args.args[1]), 10)
        self.assertEqual(result['completed_stages'][-1], 'answer')

    def test_rerank_production_setup_only_reads_voyage_key(self):
        with patch('Code_2.functions.qa.pipeline.service_key', return_value='fake') as key, \
                patch('voyageai.Client', return_value=self.client), \
                patch('Code_2.functions.qa.pipeline.GeminiAnswerer') as gemini:
            result = ask('原題', self.settings, mode='rerank', index=INDEX,
                         provider_factory=lambda *a: self.provider, store_factory=lambda *a, **k: self.store)
        self.assertEqual(result['status'], 'reranked')
        self.assertEqual([c.args[1] for c in key.call_args_list], ['VOYAGE_API_KEY'])
        gemini.assert_not_called()

    def test_voyage_retrieve_still_embeds_query_but_no_rerank(self):
        index = deepcopy(INDEX)
        index['backend'] = index['signature']['model']['backend'] = 'voyage'
        self.provider.profile = index['signature']['model']
        self.provider.embed_query.return_value = [1., 0.]
        factory = Mock(return_value=self.provider)
        result = ask('原題', self.settings, mode='retrieve', backend='voyage', index=index,
                     provider_factory=factory, store_factory=lambda *a, **k: self.store, service_factory=self.services)
        self.assertEqual(result['status'], 'retrieved')
        self.provider.embed_query.assert_called_once_with('原題')
        self.assertTrue(factory.call_args.args[1].allow_voyage_api)
        self.services.assert_not_called()

    def test_empty_results_are_not_failure_or_fake_rerank_completion(self):
        self.store.search.return_value = []
        for mode in ('retrieve', 'rerank'):
            result = self.run_mode(mode)
            self.assertEqual(result['status'], 'no_results')
            self.assertNotIn('rerank', result['completed_stages'])
            self.assertIn('沒有可用候選', render_answer(result))
        self.client.rerank.assert_not_called()

    def test_invalid_mode_before_any_provider_or_service(self):
        result = self.run_mode('invalid')
        self.assertEqual(result['status'], 'failed')
        self.provider.embed.assert_not_called()
        self.services.assert_not_called()

    def test_render_and_export_modes_without_invented_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(project_root=Path(folder))
            for mode, status in (('retrieve', 'retrieved'), ('rerank', 'reranked')):
                core = self.run_mode(mode)
                saved = run_question('原始問題', settings, mode=mode, ask_function=lambda *a, **k: core)
                result = saved
                from Code_2.functions.qa.answers import render_qa_report
                md = render_qa_report({**saved,'created_at':'2026-10-28T00:00:00+08:00'})
                self.assertEqual(saved['export_status'],'disabled')
                self.assertFalse((Path(folder)/'Output').exists())
                self.assertEqual(result['schema_version'], 'financial-qa/1.1')
                self.assertEqual(result['mode'], mode)
                self.assertEqual(result['status'], status)
                self.assertNotIn('answer', result)
                self.assertIn('階段執行情況', md)
                self.assertIn('所選模式不執行', md)
                self.assertIn('候選上限：50', md)
                self.assertIn('回答證據上限：10', md)
                self.assertNotIn('問答失敗', md)
                if mode == 'retrieve':
                    self.assertNotIn('重排序尚未完成', md)

    def test_cli_mode_forwarded_and_only_allowed_with_ask(self):
        for mode in ('retrieve', 'rerank', 'answer'):
            with patch('Code_2.main.run_question', return_value=self.run_mode(mode)) as run, patch('builtins.print'):
                self.assertEqual(main(['--ask', '原始問題', '--qa-mode', mode]), 0)
                self.assertEqual(run.call_args.kwargs['mode'], mode)
        with self.assertRaises(SystemExit), patch('sys.stderr'):
            main(['--qa-mode', 'retrieve'])

    def test_interactive_mode_forwarded_without_running_api(self):
        for selection, mode in (('1', 'retrieve'), ('2', 'rerank'), ('3', 'answer')):
            counts = [''] if mode == 'retrieve' else ['', '']
            with patch('builtins.input', side_effect=[selection, '1', '', '', *counts, '原題']), \
                    patch('Code_2.main.list_indexes', return_value=[{**INDEX, 'doc_ids': ['doc'], 'chunk_count': 50}]), \
                    patch('Code_2.main.run_question', return_value=self.run_mode(mode)) as run, \
                    patch('builtins.print'):
                interactive_qa(Settings())
                self.assertEqual(run.call_args.kwargs['mode'], mode)

    def test_custom_counts_reach_core_and_report_without_prompting(self):
        from dataclasses import replace
        qa = replace(QASettings(), retrieve_k=7, evidence_k=3)
        self.store.search.return_value = self.store.search.return_value[:7]
        self.reranker.settings = qa
        self.client.rerank.return_value.results = self.client.rerank.return_value.results[:3]
        with patch('builtins.input', side_effect=AssertionError('核心不能呼叫實驗選單')):
            result = self.run_mode('answer', qa=qa)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(self.store.search.call_args.kwargs['n_results'], 7)
        self.assertEqual(self.client.rerank.call_args.kwargs['top_k'], 3)
        self.assertEqual(len(self.answerer.answer.call_args.args[1]), 3)
        self.assertEqual((result['retrieve_k'], result['evidence_k']), (7, 3))
        from Code_2.functions.qa.answers import render_qa_report
        report = render_qa_report({**result, 'created_at': '測試時間'})
        self.assertIn('候選上限：7', report)
        self.assertIn('回答證據上限：3', report)

    def test_retrieve_does_not_validate_unused_rerank_against_smaller_topk(self):
        from dataclasses import replace
        result = self.run_mode('retrieve', qa=replace(QASettings(), retrieve_k=2))
        self.assertEqual(result['status'], 'retrieved')
        self.services.assert_not_called()


if __name__ == '__main__':
    unittest.main()

