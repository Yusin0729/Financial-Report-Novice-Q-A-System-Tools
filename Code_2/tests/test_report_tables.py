"""九頁作圖表：本機合成評分，不呼叫模型。"""
import copy
import io
import unittest
import zipfile
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from Code_2.functions.experiments.report_tables import build_tables,NAMES
from Code_2.functions.experiments.eval_run import excel_report


def stage(rank=2,raw=10,rule='numbers-only/1.0'):
    return {'raw_score':raw,'score':raw*.9,'scoring_rule':rule,'target_hits':{'目標':rank} if raw else {},
            'target_coverage':'1/1' if raw else '0/1','missing_targets':[] if raw else ['目標'],
            'contributions':[{'rank':rank,'raw_score':raw,'score':raw*.9}] if raw else [],'top20':[]}


def result(name='G1'):
    return {'schema_version':'financial-evaluation/1.0','scoring_rule':'numbers-only/1.0',
            'settings':{'retrieve_k':50,'evidence_k':10,'backend':'bge'},
            'index':{'display_name':name,'signature':{'chunking':{'mode':'parent_child','recursive_threshold':250},
                       'embedding_context_modes':{'text':'body','table':'full'}}},
            'rows':[{'ID':'1','Question':'問題1','reference':{'Evidence_Type':'table'},'status':'retrieved',
                     'scores':{'retrieval':stage(3),'returned':stage(4)}}]}


def dictionaries(tables,name):
    rows=dict(tables)[name]
    return [dict(zip(rows[0],r)) for r in rows[1:]]


class ReportTablesTests(unittest.TestCase):
    def test_nine_sheets_and_no_full_chunk_or_answer(self):
        r=result();r['rows'][0]['reference']['Answer']='秘密答案'
        r['rows'][0]['scores']['retrieval']['top20']=[{'chunk_id':'c1','text':'秘密全文'}]
        tables=build_tables([('來源',r)])
        self.assertEqual([n for n,_ in tables],list(NAMES))
        self.assertNotIn('秘密全文',str(tables));self.assertNotIn('秘密答案',str(tables))
        self.assertEqual(len(dict(tables)[NAMES[5]]),1)
        for _,rows in tables:
            self.assertTrue(all(len(row)==len(rows[0]) for row in rows))
        with zipfile.ZipFile(io.BytesIO(excel_report(r))) as z:
            self.assertEqual(sum(n.startswith('xl/worksheets/') for n in z.namelist()),9)
            self.assertIn('xl/styles.xml',z.namelist())

    def test_mixed_separate_and_overall_not_double_counted(self):
        r=result();mixed=copy.deepcopy(r['rows'][0]);mixed['ID']='2';mixed['Question']='問題2';mixed['reference']['Evidence_Type']='mixed'
        r['rows'].append(mixed)
        rows=dictionaries(build_tables([('來源',r)]),NAMES[1])
        values={x['題型']:x['共同計分題數'] for x in rows if x['階段']=='檢索子項'}
        self.assertEqual(values,{'整體':2,'表格':1,'混用':1})

    def test_common_cohort_excludes_failed_not_as_zero(self):
        a=result();a['rows'].append(copy.deepcopy(a['rows'][0]));a['rows'][1]['ID']='2';a['rows'][1]['Question']='問題2'
        b=copy.deepcopy(a);b['index']['display_name']='G2';b['rows'][1]['status']='failed'
        rows=dictionaries(build_tables([('a',a),('b',b)]),NAMES[1])
        self.assertTrue(all(x['共同計分題數']==1 for x in rows))
        self.assertTrue(all(x['原始平均']==10 for x in rows))
        self.assertTrue(any(x['未納入題數']==1 for x in rows))

    def test_version_groups_and_pending_not_failure(self):
        a=result();b=copy.deepcopy(a);b['rows'][0]['scores']['returned']['scoring_rule']='year-title-numbers/1.2'
        a['rows'][0]['scores']['returned'].update(raw_score=None,score=None)
        rows=dictionaries(build_tables([('a',a),('b',b)]),NAMES[4])
        self.assertEqual(next(x for x in rows if x['來源']=='a' and x['階段']=='召回父項後')['成功狀態'],'不計分')
        self.assertNotEqual(*[x['比較群'] for x in rows if x['階段']=='召回父項後'])

    def test_curves_count_and_five_rank_gains(self):
        tables=build_tables([('a',result())]);curves=[x for x in dictionaries(tables,NAMES[2]) if x['階段']=='檢索子項' and x['題型']=='整體']
        self.assertEqual(len(curves),50);self.assertEqual(curves[1]['原始平均'],0)
        self.assertEqual(curves[2]['完全命中率'],1)
        blocks=[x for x in dictionaries(tables,NAMES[3]) if x['階段']=='檢索子項' and x['題型']=='整體']
        self.assertEqual(sum(x['原始增分'] for x in blocks),10)

    def test_rerank_same_top_ten_and_cost_unknown_not_zero(self):
        r=result();row=r['rows'][0];row['scores']['returned']=stage(15);row['scores']['rerank']=stage(2)
        tables=build_tables([('a',r)]);summary=dictionaries(tables,NAMES[5])[0]
        self.assertEqual(summary['檢索原始平均'],0);self.assertEqual(summary['重排原始平均'],10)
        cost=dictionaries(tables,NAMES[8])[0]
        self.assertIsNone(cost['重排API tokens總數']);self.assertIsNone(cost['平均重排秒數'])
        row['timings']={'rerank':2};row['query']={'rerank':{'total_tokens':1000}}
        cost=dictionaries(build_tables([('a',r)]),NAMES[8])[0]
        self.assertEqual(cost['重排API tokens總數'],1000);self.assertEqual(cost['原始每千token提升'],10)

    def test_rerank_different_score_versions_no_delta(self):
        r=result();r['rows'][0]['scores']['rerank']=stage(rule='year-title-numbers/1.2')
        tables=build_tables([('a',r)])
        row=dictionaries(tables,NAMES[7])[0]
        self.assertIsNone(row['原始差']);self.assertIn('版本不同',row['配對說明'])
        self.assertEqual(len(dict(tables)[NAMES[5]]),1)

    def test_failed_excel_keeps_full_json_for_recovery(self):
        from Code_2.functions.experiments.eval_run import export_batch
        with tempfile.TemporaryDirectory() as tmp:
            paths={'json':Path(tmp)/'result.json','markdown':Path(tmp)/'answer.md'}
            with patch('Code_2.functions.experiments.eval_run.render_report',return_value='摘要'), patch('Code_2.functions.experiments.eval_run.excel_report',side_effect=ValueError('too large')):
                with self.assertRaises(ValueError):export_batch(paths,result())
            saved=json.loads(paths['json'].read_text(encoding='utf-8'))
            self.assertEqual(saved['export_status'],'partial')
            self.assertEqual(saved['rows'][0]['ID'],'1')

    def test_model_inputs_select_children_before_parent_without_reference(self):
        from Code_2.functions.experiments.model_input_reports import payloads
        r=result();row=r['rows'][0];row['reference']['Answer']='不能洩漏'
        children=[{'id':f'C{i}','chunk_id':f'c{i}','doc_id':'2024Q4_2330_Financial_Report',
                   'page':[1],'text':f'child {i}','parent_id':'p' if i<10 else None,'retrieval_rank':i}
                  for i in range(1,12)]
        parent={'id':'S1','chunk_id':'p','doc_id':'2024Q4_2330_Financial_Report','page':[1],
                'text':'父項全文','parent_relation':'content','matched_chunk_ids':['c1']}
        row['query']={'mode':'retrieve','retrieved_children':children,'retrieved_evidence':[parent],
                      'selected_child_ids':[c['chunk_id'] for c in children[:10]]}
        with tempfile.TemporaryDirectory() as tmp:
            paths={'json':Path(tmp)/'result.json','project_root':Path(tmp)}
            files=payloads(paths,r)
            js=json.loads(files[Path(tmp)/'ID_001.json']);md=files[Path(tmp)/'ID_001.md'].decode()
            self.assertEqual(len(js['candidates']),11)
            self.assertNotIn('reference',js);self.assertNotIn('scores',js)
            self.assertNotIn('不能洩漏',md);self.assertNotIn('child 11',md)
            self.assertEqual(md.count('父項全文'),1)
            self.assertIn('實際2組',md)


if __name__=='__main__':unittest.main()
