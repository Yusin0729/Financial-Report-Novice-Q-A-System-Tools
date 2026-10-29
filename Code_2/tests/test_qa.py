"""問答離線測試；假API、假向量；實際Chroma僅使用本次暫存目錄。"""
import json
import tempfile
import unittest
import urllib.error
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from Code_2.config.embedding import Settings, INDEX_RULE, PREPARE_RULE
from Code_2.config.qa import QASettings
from Code_2.functions.qa.answers import calculate, validate_answer, render_answer
from Code_2.functions.qa.catalog import list_indexes, select_index
from Code_2.functions.qa.pipeline import ask, build_filters, evidence_rows
from Code_2.functions.qa.services import VoyageReranker, GeminiAnswerer, NoRedirect
from Code_2.functions.embedding.keys import service_key
from Code_2.functions.embedding.providers import VoyageProvider
from Code_2.main import main


PROFILE = {'backend': 'bge', 'model': 'offline-only', 'dimension': 2}
SIGNATURE = {'rule': INDEX_RULE, 'model': PROFILE, 'preparation_rule': PREPARE_RULE,
             'fields': [('embedding_text', 'embedding'), ('metadata.stock_code', 'metadata'),
                        ('metadata.years', 'metadata')]}
INDEX = {'backend': 'bge', 'collection': 'test', 'signature': SIGNATURE}
TEXT = '2025年新臺幣千元營收1,200；2024年新臺幣千元營收1,000。'


def source():
    return {'id': 'S1', 'chunk_id': 'doc__c00001', 'doc_id': 'doc', 'page': [15, 16], 'text': TEXT,
            'retrieval_rank': 1, 'retrieval_distance': 0.1}


def response():
    return {'status': 'answered', 'reason': '', 'claims': [
        {'text': '2025年營收為1,200千元。', 'kind': 'quoted',
         'citations': [{'id': 'S1', 'quote': TEXT}]}], 'calculations': []}


def raw_row():
    return {'chunk_id': 'doc__c00001', 'distance': 0.1,
            'metadata': {'_sys_chunk_id': 'doc__c00001', '_sys_doc_id': 'doc', '_sys_input_sha256': 'a' * 64},
            'payload': {'schema_version': 'financial-vector-payload/1.0', 'input_sha256': 'a' * 64,
                        'original_chunk': {'chunk_id': 'doc__c00001', 'doc_id': 'doc', 'page': [15, 16],
                                           'content': TEXT, 'title': {'main_title': '附註', 'heading': {
                                               'text': '營收', 'children': []}}, 'source_spans': [{'start': 0, 'end': 50}]}}}


class AnswerTests(unittest.TestCase):
    def plan(self):
        return {'id': 'calc1', 'expression': 'x0-x1', 'operands': [
            {'value': '1,200', 'unit': '新臺幣千元', 'period': '2025年', 'citation': {'id': 'S1', 'quote': TEXT}},
            {'value': '1,000', 'unit': '新臺幣千元', 'period': '2024年', 'citation': {'id': 'S1', 'quote': TEXT}}]}

    def test_real_quote_and_source_render(self):
        answer = validate_answer(response(), [source()])
        text = render_answer({'status': 'answered', 'answer': answer, 'evidence': [source()]})
        self.assertIn('PDF實體頁序 15, 16', text)
        self.assertIn('doc__c00001', text)

    def test_fabricated_id_or_quote_rejected(self):
        for cite in ({'id': 'missing', 'quote': TEXT}, {'id': 'S1', 'quote': '不存在的數字9999'}):
            answer = response()
            answer['claims'][0]['citations'] = [cite]
            with self.assertRaises(ValueError):
                validate_answer(answer, [source()])

    def test_uncited_claim_and_empty_answer_rejected(self):
        for claims in ([], [{'text': '結論', 'kind': 'quoted', 'citations': []}]):
            answer = response()
            answer['claims'] = claims
            with self.assertRaises(ValueError):
                validate_answer(answer, [source()])

    def test_model_calculated_or_invented_number_rejected(self):
        answer = response()
        answer['claims'][0]['text'] = '年增率為20%。'
        with self.assertRaisesRegex(ValueError, '須交程式計算'):
            validate_answer(answer, [source()])

    def test_decimal_difference_and_placeholder(self):
        answer = response()
        answer['calculations'] = [self.plan()]
        answer['claims'][0].update(text='差額為{{calc1}}', kind='calculated')
        result = validate_answer(answer, [source()])
        self.assertEqual(result['calculations'][0]['result'], '200')
        self.assertIn('200（新臺幣千元）', result['claims'][0]['text'])

    def test_unit_period_missing_or_numeric_substring_rejected(self):
        for field, value in (('unit', '美元'), ('period', 'unknown'), ('value', '200')):
            plan = self.plan()
            plan['operands'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                calculate(plan, {'S1': source()})

    def test_no_arbitrary_code_constants_or_division_by_zero(self):
        for expr in ('__import__("os")', 'x0**x1', 'x0+100', 'x0/(x1-x1)', 'x0'):
            plan = self.plan()
            plan['expression'] = expr
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                calculate(plan, {'S1': source()})

    def test_incompatible_units_rejected(self):
        plan = self.plan()
        plan['operands'][1]['unit'] = '元'
        with self.assertRaises(ValueError):
            calculate(plan, {'S1': source()})

    def test_insufficient_requires_reason(self):
        answer = {'status': 'insufficient_evidence', 'reason': '缺少客戶明細', 'claims': [], 'calculations': []}
        self.assertEqual(validate_answer(answer, [source()])['status'], 'insufficient_evidence')
        answer['reason'] = ''
        with self.assertRaises(ValueError):
            validate_answer(answer, [source()])

    def test_partial_answer_keeps_supported_claim_before_missing_information(self):
        answer = response()
        answer.update(status='insufficient_evidence', reason='缺少客戶別營收明細，無法回答最大客戶占比。')
        valid = validate_answer(answer, [source()])
        self.assertEqual(len(valid['claims']), 1)
        text = render_answer({'status': valid['status'], 'answer': valid, 'evidence': [source()]})
        self.assertIn('有證據支持的部分', text)
        self.assertIn('缺少的資料／尚無法確認的部分', text)
        self.assertLess(text.index('1,200千元'), text.index('缺少客戶別'))
        self.assertIn('PDF實體頁序', text)


class ServiceTests(unittest.TestCase):
    def test_rerank_full_input_no_truncation_and_separate_ranks(self):
        client = Mock()
        client.rerank.return_value = SimpleNamespace(results=[SimpleNamespace(index=0, relevance_score=0.8)], total_tokens=9000)
        item = source()
        item['text'] = '完整長表格' * 4000
        rows, usage = VoyageReranker(client, QASettings()).rerank('原題', [item])
        self.assertFalse(client.rerank.call_args.kwargs['truncation'])
        self.assertEqual(client.rerank.call_args.kwargs['documents'], [item['text']])
        self.assertEqual(rows[0]['retrieval_rank'], 1)
        self.assertEqual(rows[0]['rerank_score'], 0.8)
        self.assertEqual(usage['total_tokens'], 9000)

    def test_rerank_error_never_echoes_key_or_body(self):
        client = Mock()
        client.rerank.side_effect = RuntimeError('SECRET financial body')
        with self.assertRaises(RuntimeError) as error:
            VoyageReranker(client, QASettings()).rerank('問題', [source()])
        self.assertNotIn('SECRET', str(error.exception))
        self.assertEqual(client.rerank.call_count, 1)

    def test_invalid_rerank_index_score_or_count(self):
        for results in ([], [SimpleNamespace(index=4, relevance_score=0.8)],
                        [SimpleNamespace(index=0, relevance_score=float('nan'))]):
            client = Mock()
            client.rerank.return_value = SimpleNamespace(results=results)
            with self.assertRaises(ValueError):
                VoyageReranker(client, QASettings()).rerank('問題', [source()])

    def answerer(self, *, tokens=100, finish='STOP', body=None):
        answerer = GeminiAnswerer('FAKE-KEY', QASettings())
        answerer.post = Mock(side_effect=[{'totalTokens': tokens}, {
            'modelVersion': 'fake', 'usageMetadata': {'totalTokenCount': 150},
            'candidates': [{'finishReason': finish, 'content': {'parts': [
                {'text': json.dumps(response() if body is None else body)}]}}]}])
        return answerer

    def test_gemini_full_evidence_count_before_generation(self):
        a = self.answerer()
        result, usage = a.answer('原始問題', [source()])
        self.assertEqual(result['status'], 'answered')
        counted = a.post.call_args_list[0].args[1]['generateContentRequest']
        self.assertIn(TEXT, counted['contents'][0]['parts'][0]['text'])
        self.assertEqual(a.post.call_args_list[1].args[1]['contents'], counted['contents'])
        self.assertNotIn('tools', counted)
        self.assertEqual(usage['input_tokens'], 100)

    def test_over_budget_never_generates(self):
        a = self.answerer(tokens=32001)
        with self.assertRaisesRegex(ValueError, '未截斷'):
            a.answer('問題', [source()])
        self.assertEqual(a.post.call_count, 1)
        self.assertEqual(a.last_attempt['input_tokens'], 32001)

    def test_truncated_or_blocked_answer_rejected(self):
        for finish in ('MAX_TOKENS', 'SAFETY'):
            with self.assertRaises(ValueError):
                self.answerer(finish=finish).answer('問題', [source()])

    def test_http_429_stops_no_retry_no_body_or_key(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('url', 429, 'SECRET body', {}, None)
        a = GeminiAnswerer('FAKE-KEY', QASettings(), opener)
        with self.assertRaisesRegex(RuntimeError, '429') as error:
            a.post('generateContent', {})
        self.assertNotIn('SECRET', str(error.exception))
        self.assertEqual(opener.open.call_count, 1)
        self.assertNotIn('FAKE-KEY', opener.open.call_args.args[0].full_url)

    def test_redirect_refused(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other'))

    def test_voyage_query_mode_prefix_no_truncation(self):
        client = Mock()
        client.count_tokens.return_value = 10
        client.embed.return_value = SimpleNamespace(embeddings=[[1.] + [0.] * 1023])
        provider = VoyageProvider(client=client, model_name='voyage-finance-2', max_tokens=32000, batch_tokens=120000)
        self.assertEqual(len(provider.embed_query('原題')), 1024)
        self.assertEqual(client.embed.call_args.kwargs['input_type'], 'query')
        self.assertFalse(client.embed.call_args.kwargs['truncation'])
        self.assertIn('Represent the query', client.count_tokens.call_args.args[0][0])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.provider = Mock(profile=PROFILE)
        self.provider.embed.return_value = [[1., 0.]]
        self.store = Mock(collection_name='test')
        self.store.search.return_value = [raw_row()]
        self.reranker = Mock()
        self.reranker.rerank.side_effect = lambda q, rows: (rows, {'model': 'offline-only'})
        self.answerer = Mock()
        self.answerer.answer.return_value = (response(), {'model': 'offline-only'})

    def run_ask(self, **kwargs):
        return ask('原始問題', Settings(), index=INDEX,
                   provider_factory=lambda *a: self.provider, store_factory=lambda *a, **k: self.store,
                   service_factory=lambda *a: (self.reranker, self.answerer), **kwargs)

    def test_pipeline_preserves_original_and_filters(self):
        result = self.run_ask(stock_code='0050', report_year=2025)
        self.assertEqual(result['status'], 'answered')
        self.assertFalse(result['rewrite_enabled'])
        self.provider.embed.assert_called_once_with(['原始問題'], batch_size=1)
        self.assertEqual(self.store.search.call_args.kwargs['where'], {'$and': [{'stock_code': '0050'}, {'years': {'$contains': 2025}}]})
        self.assertEqual(self.answerer.answer.call_args.args[0], '原始問題')
        self.store.close.assert_called_once()

    def test_no_results_skips_both_external_stages(self):
        self.store.search.return_value = []
        result = self.run_ask()
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.reranker.rerank.assert_not_called()
        self.answerer.answer.assert_not_called()

    def test_pipeline_partial_answer_and_candidate_evidence_preserved(self):
        partial = response()
        partial.update(status='insufficient_evidence', reason='缺少客戶別明細。')
        self.answerer.answer.return_value = partial, {'model': 'offline-only'}
        result = self.run_ask()
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertEqual(len(result['answer']['claims']), 1)
        self.assertIn(TEXT, result['retrieved_evidence'][0]['text'])
        self.assertEqual(result['prompt_version'], 'evidence-answer/1.1')

    def test_rerank_failure_does_not_fall_back_to_generation(self):
        self.reranker.rerank.side_effect = RuntimeError('安全錯誤')
        result = self.run_ask()
        self.assertEqual(result['stage'], 'rerank')
        self.assertEqual(result['status'], 'failed')
        self.answerer.answer.assert_not_called()

    def test_generation_failure_keeps_completed_token_precheck(self):
        self.answerer.last_attempt = {'model': 'offline-only', 'input_tokens': 32001}
        self.answerer.answer.side_effect = ValueError('超過輸入預算')
        result = self.run_ask()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['generation']['input_tokens'], 32001)
        self.assertIn(TEXT, result['evidence'][0]['text'])

    def test_signature_mismatch_stops_before_search(self):
        self.provider.profile = {**PROFILE, 'dimension': 3}
        result = self.run_ask()
        self.assertEqual(result['status'], 'failed')
        self.store.search.assert_not_called()

    def test_corrupt_payload_and_hallucinated_citation_rejected(self):
        row = raw_row()
        row['metadata']['_sys_doc_id'] = 'other'
        with self.assertRaises(ValueError):
            evidence_rows([row])
        bad = response()
        bad['claims'][0]['citations'][0]['id'] = 'S999'
        self.answerer.answer.return_value = bad, {}
        self.assertEqual(self.run_ask()['stage'], 'validate_answer')

    def test_filters_not_stored_in_signature_fail_closed(self):
        with self.assertRaises(ValueError):
            build_filters({'fields': []}, stock_code='2330')

    def test_missing_key_stops_before_model(self):
        provider = Mock()
        with patch('Code_2.functions.qa.pipeline.service_key', side_effect=ValueError('缺少VOYAGE_API_KEY')):
            result = ask('問題', Settings(), index=INDEX, provider_factory=provider)
        self.assertEqual(result['stage'], 'service_setup')
        provider.assert_not_called()

    def test_selected_index_is_unambiguous(self):
        self.assertEqual(select_index([INDEX], 'bge'), INDEX)
        with self.assertRaises(ValueError):
            select_index([INDEX, INDEX], 'bge')

    def test_list_absent_indexes_never_creates_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(project_root=Path(folder))
            self.assertEqual(list_indexes(settings), [])
            self.assertFalse(settings.vector_root.exists())

    def test_actual_chroma_catalog_and_query_only_committed_sources(self):
        from Code_2.functions.embedding.store import ChromaStore
        from Code_2.functions.embedding.prepare import prepare_document
        from Code_2.tests.test_preparation import fixture
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(project_root=Path(folder))
            root = settings.vector_root / 'bge'
            root.mkdir(parents=True)
            store = ChromaStore(root, signature=SIGNATURE)
            try:
                chunk = prepare_document(fixture(TEXT), input_sha256='a' * 64)['chunks'][0]
                item = {'chunk_id': chunk['chunk_id'], 'text': chunk['embedding_text'],
                        'metadata': chunk['metadata'], 'chroma_metadata': {'stock_code': '2330', 'years': [2025]},
                        'original_chunk': chunk['original_chunk']}
                store.commit_document(doc_id=chunk['original_chunk']['doc_id'], content_hash='hash', items=[item],
                                      vectors=[[1., 0.]], model_profile=PROFILE, input_sha256='b' * 64)
                store.collection.add(ids=['orphan'], embeddings=[[1., 0.]], documents=['{}'],
                                     metadatas=[{'_sys_run_id': 'not-committed'}])
            finally:
                store.close()
            indexes = list_indexes(settings)
            self.assertEqual(len(indexes), 1)
            self.assertEqual(indexes[0]['chunk_count'], 1)
            result = ask('營收', settings, index=indexes[0],
                         provider_factory=lambda *a: self.provider,
                         service_factory=lambda *a: (self.reranker, self.answerer), stock_code='2330', report_year=2025)
            self.assertEqual(result['status'], 'answered', result.get('error'))
            self.assertEqual(len(result['retrieval']), 1)
            self.assertNotEqual(result['retrieval'][0]['chunk_id'], 'orphan')

    def test_gemini_key_selective_parse_and_environment_priority(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            root = Path(folder)
            (root / '.env').write_text('OTHER_SECRET=not-loaded\nGEMINI_API_KEY="${LITERAL}"\nVOYAGE_API_KEY=fake\n', encoding='utf-8')
            self.assertEqual(service_key(root, 'GEMINI_API_KEY'), '${LITERAL}')
            with patch.dict('os.environ', {'GEMINI_API_KEY': 'environment-fake'}):
                self.assertEqual(service_key(root, 'GEMINI_API_KEY'), 'environment-fake')

    def test_cli_question_and_index_options(self):
        with patch('Code_2.main.run_question', return_value={'status': 'failed', 'stage': 'test', 'error': 'fake'}) as query:
            self.assertEqual(main(['--ask', '問題', '--stock-code', '0050', '--report-year', '2025']), 1)
            self.assertEqual(query.call_args.kwargs['stock_code'], '0050')
        with patch('Code_2.main.list_indexes', return_value=[]):
            self.assertEqual(main(['--list-indexes']), 0)


if __name__ == '__main__':
    unittest.main()
