"""EXPERIMENT_ONLY選單與核心隔離；輸入輸出與API皆為模擬。"""
import unittest
from unittest.mock import Mock, patch
from Code_2.config.embedding import Settings
from Code_2.config.qa import QASettings
from Code_2.functions.experiments.qa_menu import run_qa_menu
from Code_2.tests.test_qa import INDEX


class MenuTests(unittest.TestCase):
    def run_menu(self, values):
        execute = Mock(return_value={'status': 'test-only'})
        settings = Settings(export_enabled=False)
        with patch('builtins.input', side_effect=values), patch('builtins.print'):
            run_qa_menu(settings, index_loader=Mock(return_value=[INDEX]), execute=execute,
                        display_indexes=Mock(), display_result=Mock())
        return execute

    def test_manual_all_parameters_are_only_for_current_question(self):
        execute = self.run_menu(['3', '1', '0050', '2024', '30', '6', '原始問題'])
        self.assertEqual(execute.call_args.args[0], '原始問題')
        kwargs = execute.call_args.kwargs
        self.assertEqual((kwargs['stock_code'], kwargs['report_year'], kwargs['mode']), ('0050', 2024, 'answer'))
        self.assertEqual((kwargs['qa'].retrieve_k, kwargs['qa'].evidence_k), (30, 6))
        self.assertEqual((QASettings().retrieve_k, QASettings().evidence_k), (50, 10))

    def test_explicit_enter_uses_confirmed_defaults_and_no_scope(self):
        execute = self.run_menu(['2', '1', '', '', '', '', '問題'])
        kwargs = execute.call_args.kwargs
        self.assertIsNone(kwargs['stock_code'])
        self.assertIsNone(kwargs['report_year'])
        self.assertEqual((kwargs['qa'].retrieve_k, kwargs['qa'].evidence_k), (50, 10))

    def test_small_retrieve_requires_explicit_rerank_count_no_silent_minimum(self):
        execute = self.run_menu(['2', '1', '', '', '5', '', '10', '3', '問題'])
        qa = execute.call_args.kwargs['qa']
        self.assertEqual((qa.retrieve_k, qa.evidence_k), (5, 3))

    def test_invalid_counts_reprompt_before_executing(self):
        execute = self.run_menu(['3', '1', '', '', '-1', '1001', '1.5', '20', '21', 'x', '4', '問題'])
        qa = execute.call_args.kwargs['qa']
        self.assertEqual((qa.retrieve_k, qa.evidence_k), (20, 4))
        execute.assert_called_once()

    def test_retrieve_only_does_not_ask_unused_rerank_count(self):
        execute = self.run_menu(['1', '1', '2330', '', '2', '問題'])
        kwargs = execute.call_args.kwargs
        self.assertEqual(kwargs['qa'].retrieve_k, 2)
        self.assertEqual(kwargs['mode'], 'retrieve')

    def test_cancel_at_either_count_does_not_start_query(self):
        for values in (['1', '1', '', '', '0'], ['3', '1', '', '', '20', '0']):
            with self.subTest(values=values):
                self.run_menu(values).assert_not_called()

    def test_invalid_company_or_year_never_executes(self):
        for values in (['3', '1', '台積電'], ['3', '1', '', '2025Q4'], ['3', '1', '', '0']):
            with self.subTest(values=values):
                self.run_menu(values).assert_not_called()

    def test_cli_does_not_require_experiment_menu_module(self):
        from Code_2.main import main
        failure = {'status': 'failed', 'stage': 'test', 'error': 'fake', 'export_status': 'disabled'}
        with patch.dict('sys.modules', {'Code_2.functions.experiments.qa_menu': None}), \
                patch('Code_2.main.run_question', return_value=failure) as run, patch('builtins.input') as prompt, \
                patch('builtins.print'):
            self.assertEqual(main(['--ask', '原題']), 1)
            self.assertEqual(run.call_args.kwargs['mode'], 'answer')
            prompt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
