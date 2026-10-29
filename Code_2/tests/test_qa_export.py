"""問答Markdown／JSON集中保存；所有題目與API結果為合成資料。"""
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from Code_2.config.embedding import Settings
from Code_2.functions.experiments.export_output import reserve_qa_run, export_qa_run
from Code_2.functions.qa.run import run_question
from Code_2.functions.qa.answers import render_qa_report
from Code_2.tests.test_qa import source, response, TEXT


def result(status='answered'):
    answer = response()
    answer['status'] = status
    if status == 'insufficient_evidence':
        answer['reason'] = '缺少客戶別營收，無法判斷最大客戶占比。'
    candidate = source()
    second = {**source(), 'id': 'S2', 'chunk_id': 'doc__c00002', 'retrieval_rank': 2, 'text': '另一完整候選片段'}
    selected = {**candidate, 'rerank_rank': 1, 'rerank_score': 0.8}
    return {'schema_version': 'financial-qa/1.0', 'status': status, 'original_question': '營收及最大客戶占比？',
            'rewrite_enabled': False, 'prompt_version': 'evidence-answer/1.1', 'backend': 'bge',
            'collection': 'test-only', 'filters': {'$and': [{'stock_code': '0050'}, {'years': {'$contains': 2025}}]},
            'retrieve_k': 20, 'evidence_k': 5, 'retrieved_evidence': [candidate, second], 'evidence': [selected],
            'rerank_model': 'rerank-3-lite', 'answer_model': 'gemini-3.1-flash-lite', 'answer': answer,
            'rerank': {'total_tokens': 123}, 'generation': {'input_tokens': 456, 'model_version': 'fake-only',
                                                         'usage': {'promptTokenCount': 456, 'totalTokenCount': 500}}}


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings=Settings(project_root=Path(self.tmp.name))

    def test_single_modes_never_create_reports_even_when_export_enabled(self):
        for mode in ('retrieve','rerank','answer'):
            original=result();before=deepcopy(original)
            with patch('Code_2.functions.experiments.export_output.reserve_qa_run',side_effect=AssertionError('不得建立測報目錄')), patch('Code_2.functions.experiments.export_output.export_qa_run',side_effect=AssertionError('不得寫檔')):
                value=run_question('測試題',self.settings,mode=mode,ask_function=lambda *a,**k:original)
            self.assertEqual(original,before)
            self.assertEqual(value['export_status'],'disabled')
            self.assertEqual(value['answer'],original['answer'])
            self.assertNotIn('output_dir',value)
            self.assertFalse((self.settings.project_root/'Output').exists())

    def test_single_failure_or_missing_evidence_stays_in_response(self):
        for status in ('failed','insufficient_evidence'):
            value=run_question('題目',self.settings,ask_function=lambda *a,**k:result(status))
            self.assertEqual(value['status'],status)
            self.assertEqual(value['export_status'],'disabled')
            self.assertFalse((self.settings.project_root/'Output').exists())

    def test_single_core_error_is_safely_returned_without_files(self):
        for error in (RuntimeError('SECRET-KEY'),KeyboardInterrupt()):
            value=run_question('題目',self.settings,ask_function=Mock(side_effect=error))
            self.assertEqual(value['stage'],'question_execution')
            self.assertNotIn('SECRET-KEY',str(value))
            self.assertFalse((self.settings.project_root/'Output').exists())

    def test_explicit_legacy_report_export_still_available(self):
        stamp=datetime(2026,10,22,1,2,3,456789,tzinfo=timezone.utc)
        paths=reserve_qa_run(self.settings,now=stamp)
        self.assertEqual(paths['json'].parent.name,'qa_20261022_09-02-03_456789')
        export_qa_run(self.settings,paths,result())
        before=paths['json'].read_bytes()
        with self.assertRaises(FileExistsError):export_qa_run(self.settings,paths,result())
        self.assertEqual(paths['json'].read_bytes(),before)

    def test_cli_no_export_remains_compatible(self):
        from Code_2.main import main
        with patch('Code_2.main.run_question',return_value={**result(),'export_status':'disabled'}) as run:
            self.assertEqual(main(['--ask','題目','--no-export']),0)
        self.assertFalse(run.call_args.args[1].export_enabled)


if __name__=='__main__':unittest.main()
