"""多索引及事後圖表：本機假查詢，不呼叫模型或使用者索引。"""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from Code_2.config.embedding import Settings
from Code_2.functions.web.service import validate_task,execute_task,task_outcome,report_path
from Code_2.functions.web.comparison import run_comparison
from Code_2.functions.experiments.chart_report import validate_source,make_report
from Code_2.functions.experiments.eval_scoring import score
from Code_2.tests.test_evaluation import row,candidate,A


class ComparisonChartsTests(unittest.TestCase):
    def query(self):
        return dict(action='query',question='同一問題',mode='retrieve',retrieve_k=50,evidence_k=10,
            indexes=[{'backend':'bge','collection':'financial_'+'a'*24},
                     {'backend':'bge','collection':'financial_'+'b'*24}])
    def test_validation_and_independent_sequential_results(self):
        settings=Settings();task=validate_task(self.query(),settings)
        self.assertIn('export_enabled',task)
        calls=[]
        def fake(data,settings):
            calls.append(data)
            return {'action':'query','query':{'status':'retrieved','collection':data['collection']}}
        with patch('Code_2.functions.web.comparison.list_indexes',return_value=[]),patch('Code_2.functions.web.comparison.select_index') as select:
            result=run_comparison(task,settings,fake)
        self.assertEqual(select.call_count,2)
        self.assertEqual([d['question'] for d in calls],['同一問題']*2)
        self.assertEqual([d['collection'] for d in calls],[i['collection'] for i in task['indexes']])
        self.assertTrue(all('indexes' not in d for d in calls))
        self.assertEqual(task_outcome(result),'completed')
        bad=self.query();bad['indexes']*=2
        with self.assertRaises(ValueError):validate_task(bad,settings)
    def test_failed_index_stops_following_calls(self):
        task=validate_task(self.query(),Settings())
        with patch('Code_2.functions.web.comparison.list_indexes',return_value=[]),patch('Code_2.functions.web.comparison.select_index'):
            calls=[]
            def fake(data,settings):
                calls.append(data);return {'action':'query','query':{'status':'failed'}}
            result=run_comparison(task,Settings(),fake)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['results'][1]['outcome'],'not_run')
        self.assertEqual(task_outcome(result),'needs_attention')
    def source(self):
        ref=row();ref['expected_titles']=[A]
        s=score(ref,[candidate('a',[A])],retrieve_k=50)
        return {'schema_version':'financial-evaluation/1.0','scoring_rule':'year-title-dual/2.0',
            'filename':'測試.xlsx','sheet':'題目','settings':{'retrieve_k':50},
            'summary':{'mean_score':10,'mean_raw_score':10,'mean_weighted_score':10,'scored':1,'selected':1},
            'rows':[{'ID':'1','Question':'問題','status':'retrieved','score':10,'raw_score':10,
                'weighted_score':10,'score_stage':'returned','scores':{'returned':s}}]}
    def test_post_chart_new_folder_artifacts_preserve_source(self):
        with tempfile.TemporaryDirectory() as temp:
            settings=replace(Settings(),project_root=Path(temp),export_enabled=False)
            name='qa_20261027_00-00-00_000001'
            folder=settings.response_dir/name;folder.mkdir(parents=True)
            original=json.dumps(self.source(),ensure_ascii=False).encode()
            (folder/'result.json').write_bytes(original)
            (folder/'answer.md').write_text('保留原結果',encoding='utf-8')
            task=validate_task({'action':'make-charts','source_run':name},settings)
            # worker validates again; lineage must survive.
            task=validate_task(task,settings)
            result=execute_task(task,settings)
            report=result['evaluation'];target=Path(report['output_dir'])
            self.assertNotEqual(target,folder)
            self.assertEqual((folder/'result.json').read_bytes(),original)
            self.assertEqual((folder/'answer.md').read_text(encoding='utf-8'),'保留原結果')
            self.assertEqual(report['source_run'],name)
            for file in ('result.json','answer.md','results.xlsx','charts.svg'):
                self.assertEqual(report_path(settings,target.name,file),target/file)
            self.assertIn('<polyline', (target/'charts.svg').read_text(encoding='utf-8'))
            with zipfile.ZipFile(target/'results.xlsx') as z:
                self.assertIn('檢索TopK曲線',z.read('xl/workbook.xml').decode())
            self.assertEqual(task_outcome(result),'completed')
    def test_unsaved_result_and_invalid_or_disabled_sources(self):
        source=self.source()
        clean=validate_source({'source':source},Settings())
        self.assertEqual(len(clean['rows'][0]['scores']['returned']['top20']),0)
        source['rows'][0]['scores']['returned']['contributions'][0]['raw_score']=-1
        with self.assertRaises(ValueError):validate_source({'source':source},Settings())
        with self.assertRaises(ValueError):validate_source({'source_run':'../bad'},Settings())
        with patch('Code_2.functions.experiments.chart_report.EvaluationSettings',return_value=type('C',(),{'enabled':False})()):
            with self.assertRaisesRegex(ValueError,'停用'):validate_source({'source':self.source()},Settings())

if __name__=='__main__':unittest.main()
