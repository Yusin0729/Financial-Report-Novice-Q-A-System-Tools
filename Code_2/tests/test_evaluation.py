"""批次實驗本機驗證；合成資料／假查詢，不呼叫模型、不操作使用者索引。"""
import base64,json,tempfile,unittest,zipfile,io
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from Code_2.config.embedding import Settings
from Code_2.functions.experiments.eval_workbook import HEADERS,write_xlsx,read_upload,titles
from Code_2.functions.experiments.eval_curve import build_curves
from Code_2.functions.experiments.eval_scoring import score
from Code_2.functions.experiments.eval_run import run_batch
from Code_2.functions.experiments.analysis_guide import render_analysis_guide
from Code_2.functions.experiments.question_reports import payloads as question_payloads
from Code_2.functions.web.service import validate_task,report_path
from Code_2.config.qa import QASettings
from Code_2.functions.qa.pipeline import build_filters

A='七、金融資產';B='十、避險工具'
def upload(rows,headers=HEADERS):
    return base64.b64encode(write_xlsx([('題目',[list(headers)]+rows)])).decode()
def values(i='1',q='問題',page='2024_2330_P50',title=A+'; '+B):
    return [i,q,'參考答案不得進模型',page,'202404_2330_AI1.pdf','2023, 2024','大標','不同名稱',title]
def row():return read_upload(upload([values()]),'測試.xlsx')['rows'][0]
def candidate(cid,titles=(),page=(50,),years=(2023,2024),parent=None):
    return {'chunk':{'chunk_id':cid,'doc_id':'2024Q4_2330_Financial_Report','years':list(years),
        'page':list(page),'note_title':list(titles),'parent_id':parent},'text':'證據'+cid}
class EvaluationTests(unittest.TestCase):
    def test_independent_report_and_question_rerank_scores(self):
        ref=row();ref.update(Evidence_Type='table',Cross_Page_Table='unknown')
        retrieved=score(ref,[candidate('miss'),candidate('hit',[A,B])],retrieve_k=50)
        reranked=score(ref,[candidate('hit',[A,B])],retrieve_k=50)
        result={'schema_version':'financial-evaluation/1.0','scoring_rule':'year-title-dual/3.1',
                'filename':'測試.xlsx','sheet':'題目','source_sha256':'abc','status':'completed',
                'settings':{'mode':'rerank','retrieve_k':50,'evidence_k':10},
                'index':{'backend':'bge','collection':'test'},'elapsed_seconds':2,
                'source_run':'source-run','report_kind':'saved_rerank',
                'summary':{'scored':1,'failed':0,'not_run':0},
                'rows':[{'ID':'1','Question':'問題','reference':ref,'status':'reranked',
                         'score_stage':'rerank','elapsed_seconds':1,'scores':{
                             'retrieval':retrieved,'rerank':reranked},
                         'query':{'status':'reranked','mode':'rerank','evidence':[]}}]}
        report=render_analysis_guide(result)
        self.assertIn('獨立測試分析報告',report)
        self.assertIn('重排序',report)
        self.assertIn('原始 10.0／10；加權 10.0／10',report)
        self.assertIn('Top 1 hit',report)
        self.assertNotIn('參考答案不得進模型',report)
        with tempfile.TemporaryDirectory() as root:
            paths={'json':Path(root)/'result.json','project_root':Path(root)}
            files=question_payloads(paths,result)
            data=json.loads(files[Path(root)/'ID_001.json'])
            self.assertNotIn('scores',data)
            self.assertNotIn('reference',data)
            self.assertEqual(result['rows'][0]['scores']['rerank']['raw_score'],10)
            md=files[Path(root)/'ID_001.md'].decode('utf-8')
            self.assertIn('只依以下證據回答',md)
            self.assertNotIn('原始分數',md)
            self.assertNotIn('參考答案不得進模型',md)
    def test_workbook_contract_optional_filters_and_exclusions(self):
        blank=['2','另一題','','','','','','','']
        book=read_upload(upload([values(),values('26'),blank]),'測試.xlsx')
        self.assertEqual(book['valid_count'],2)
        self.assertEqual(book['rows'][0]['filter_years'],[2023,2024])
        self.assertEqual(book['rows'][0]['stock_code'],'2330')
        self.assertTrue(book['rows'][1]['excluded'])
        self.assertEqual(book['rows'][2]['filter_years'],[])
        self.assertIsNone(book['rows'][2]['stock_code'])
    def test_multi_title_boundaries_keep_punctuation_inside_titles(self):
        self.assertEqual(titles('二八、費用性質之額外資訊, 三十、現金流量資訊'),
                         ['二八、費用性質之額外資訊','三十、現金流量資訊'])
        self.assertEqual(titles('七、金融資產，十、避險工具'),['七、金融資產','十、避險工具'])
        self.assertEqual(titles('十四、不動產、廠房及設備'),['十四、不動產、廠房及設備'])
        self.assertEqual(titles('二二、營業收入 、資產總計'),['二二、營業收入 、資產總計'])
        self.assertEqual(titles('1. Property, plant and equipment; 2. Revenue'),
                         ['1. Property, plant and equipment','2. Revenue'])
        self.assertEqual(titles('（一）營收,（二）費用'),['（一）營收','（二）費用'])
    def test_invalid_and_duplicate_rows_not_silently_run(self):
        book=read_upload(upload([values(),values(q='')]),'測試.xlsx')
        self.assertTrue(all(r['errors'] for r in book['rows']))
        with self.assertRaises(ValueError):read_upload('bad','測試.xlsx')
        with self.assertRaises(ValueError):read_upload(upload([]),'測試.xls')
        with self.assertRaises(ValueError):read_upload(upload([],['ID']),'測試.xlsx')
    def test_confirmed_rank_examples(self):
        r=row();r['filter_years']=[];a=candidate('a',[A]);b=candidate('b',[B]);other=candidate('x')
        for entries,want in (([a,b],10),([a,other,b],9.75),([other,a,b],9.5)):
            self.assertEqual(score(r,entries)['score'],want)
        r['expected_titles']=[A]
        self.assertEqual(score(r,[other,a])['score'],9.5)
    def test_rank_penalty_uses_requested_retrieval_count(self):
        r=row();r['filter_years']=[];r['expected_titles']=[A]
        entries=[candidate('x'),candidate('y'),candidate('hit',[A])]
        self.assertEqual(score(r,entries,retrieve_k=50)['score'],9.6)
        self.assertEqual(score(r,entries,retrieve_k=20)['score'],9)
        late=[candidate('x'+str(i)) for i in range(24)]+[candidate('hit',[A])]
        self.assertEqual(score(r,late,retrieve_k=50)['score'],5.2)
        self.assertEqual(score(r,late,retrieve_k=20)['score'],0)
        r['expected_titles']=[A,B]
        self.assertEqual(score(r,[candidate('a',[A]),candidate('x'),candidate('b',[B])],retrieve_k=50)['score'],9.9)
        for invalid in (0,-1,True):
            with self.assertRaises(ValueError):score(r,entries,retrieve_k=invalid)
    def test_late_four_targets_keep_proportional_points(self):
        r=row()
        entries=[candidate('miss'+str(i)) for i in range(16)]+[candidate('a',[A])]
        entries += [candidate('later'+str(i)) for i in range(16)]+[candidate('b',[B])]
        s=score(r,entries,retrieve_k=50)
        self.assertEqual(s['raw_score'],10)
        self.assertEqual(s['score'],5.4)
        self.assertEqual(s['rank_penalty'],0.05)
        self.assertTrue(all(c['score']>0 for c in s['contributions']))
        curves=build_curves([{'status':'retrieved','scores':{'returned':s}}],50)
        self.assertEqual(curves['returned']['points'][-1]['mean_score'],5.4)
    def test_curves_do_not_claim_one_penalty_for_different_target_counts(self):
        r=row();four=score(r,[],retrieve_k=50)
        r['expected_titles']=[A];r['filter_years']=[]
        one=score(r,[],retrieve_k=50)
        curve=build_curves([{'status':'retrieved','scores':{'returned':s}} for s in (four,one)],50)['returned']
        self.assertIsNone(curve['rank_penalty'])
        self.assertEqual(curve['rank_penalties'],[0.05,0.2])
    def test_curve_fixed_penalty_cohort_blocks_and_full_result(self):
        r=row();r['filter_years']=[];r['expected_titles']=[A]
        s=score(r,[candidate('x'),candidate('y'),candidate('hit',[A])],retrieve_k=50)
        zero=score(r,[],retrieve_k=50)
        rows=[{'status':'retrieved','scores':{'retrieval':s}},
              {'status':'retrieved','scores':{'retrieval':zero}},
              {'status':'failed','scores':{'retrieval':s}}]
        c=build_curves(rows,50)['retrieval']
        self.assertEqual(c['count'],2)
        self.assertEqual(len(c['points']),50)
        self.assertEqual(c['points'][1]['mean_score'],0)
        self.assertEqual(c['points'][2]['mean_score'],4.8)
        self.assertEqual(c['points'][-1]['mean_score'],4.8)
        self.assertEqual(c['first_full_score_k'],3)
        self.assertEqual(len(c['blocks']),10)
        self.assertEqual(sum(b['gain'] for b in c['blocks']),4.8)
        self.assertEqual(c['best_block']['end'],5)
        self.assertIsNone(build_curves([rows[1]],7)['retrieval']['first_full_score_k'])
        self.assertEqual(build_curves([rows[0]],7)['retrieval']['blocks'][-1]['end'],7)
    def test_year_title_targets_partial_and_dual_scores(self):
        r=row()
        a=candidate('a',[A],years=(2023,2024))
        b=candidate('b',[B],years=(2023,))
        s=score(r,[a,b],retrieve_k=50)
        self.assertEqual(s['raw_score'],7.5)
        self.assertEqual(s['score'],7.5)
        self.assertEqual(s['target_coverage'],'3/4')
        self.assertEqual(s['missing_targets'],['2024｜'+B])
        self.assertFalse(s['complete'])
        c=candidate('c',[B],years=(2024,))
        s=score(r,[a,b,c],retrieve_k=50)
        self.assertEqual(s['raw_score'],10)
        self.assertEqual(s['score'],10)
        self.assertTrue(s['complete'])
        self.assertEqual(len(s['contributions']),4)
        delayed=score(r,[candidate('x'+str(i)) for i in range(4)]+[a,b],retrieve_k=50)
        self.assertEqual(delayed['raw_score'],7.5)
        self.assertLess(delayed['score'],7.5)
        # 年度空白不猜測，退為每標題一項。
        r['filter_years']=[]
        s=score(r,[a,b],retrieve_k=50)
        self.assertEqual(s['target_coverage'],'2/2')
        self.assertEqual(s['raw_score'],10)
    def test_raw_curve_counts_year_items_and_repeated_siblings_once(self):
        r=row();r['expected_titles']=[A]
        entries=[candidate('a',[A],years=(2023,),parent='p'),
                 candidate('aa',[A],years=(2023,),parent='p'),
                 candidate('b',[A],years=(2024,),parent='q')]
        s=score(r,entries,retrieve_k=50)
        self.assertEqual(s['target_hits'],{'2023｜'+A:1,'2024｜'+A:2})
        curves=build_curves([{'status':'retrieved','scores':{'retrieval':s}}],50,metric='raw')
        self.assertEqual(curves['retrieval']['points'][0]['mean_score'],5)
        self.assertEqual(curves['retrieval']['points'][1]['mean_score'],10)
        # 同一個chunk的兩年度可同時命中。
        both=score(r,[candidate('both',[A])],retrieve_k=50)
        self.assertEqual(both['raw_score'],10)
        self.assertEqual(both['target_coverage'],'2/2')
    def test_pages_are_reference_only_and_title_still_required(self):
        r=row()
        s=score(r,[candidate('a',[A,B],page=(49,50))])
        self.assertEqual(s['score'],10)
        self.assertEqual(s['page_coverage'],'1/1')
        s=score(r,[candidate('a',[A,B],page=(49,)),candidate('b',page=(50,))])
        self.assertEqual(s['score'],10)
        self.assertEqual(s['title_coverage'],'2/2')
        self.assertTrue(s['page_is_reference_only'])
    def test_wrong_year_or_file_is_zero_and_reference_subsection_is_unused(self):
        r=row();c=candidate('a',[A,B],years=(2022,))
        self.assertEqual(score(r,[c])['score'],0)
        c=candidate('a',[A,B]);c['chunk']['doc_id']='2023Q4_2303_Financial_Report'
        self.assertEqual(score(r,[c])['score'],0)
        self.assertEqual(score(r,[candidate('a',[A,B])])['score'],10)
    def test_target_title_matches_subsection_with_same_page_year_and_document(self):
        r=row();r['filter_years']=[];r['expected_titles']=[A]
        c=candidate('hit',['其他下層標題']);c['chunk']['sub_section']='七 、 金融資產'
        entries=[candidate('x'),candidate('y'),c]
        result=score(r,entries)
        self.assertEqual(result['score'],9)
        self.assertEqual(result['title_hits'],{A:3})
        self.assertEqual(result['top20'][2]['sub_section'],'七 、 金融資產')
        for field,value in [('years',[2022]),('doc_id','2023Q4_2303_Financial_Report')]:
            with self.subTest(field=field):
                wrong={**c,'chunk':{**c['chunk'],field:value}}
                restricted={**r,'filter_years':[2023,2024]}
                self.assertEqual(score(restricted,[wrong])['score'],0)
        # 參考Evidence_Sub_Section仍不參與；只有Evidence_Note_Title是目標。
        r['expected_titles']=[B];r['Evidence_Sub_Section']=A
        self.assertEqual(score(r,[c])['score'],0)
    def test_subsection_and_note_title_duplicate_does_not_double_score(self):
        r=row();c=candidate('a',[A]);c['chunk']['sub_section']=A
        result=score(r,[c])
        self.assertEqual(result['score'],5)
        self.assertEqual(result['title_coverage'],'1/2')
    def test_cross_report_year_numberless_titles_and_empty_page(self):
        r=row();r['expected_titles']=['二一、營業收入'];r['filter_years']=[2024];r['expected_pages']=[]
        c=candidate('a',['（二）客戶合約收入']);c['chunk'].update(doc_id='2025Q4_2330_Financial_Report',
            sub_section='二二、營業收入',years=[2024,2025],page=[99])
        s=score(r,[c],retrieve_k=50)
        self.assertEqual(s['raw_score'],10)
        self.assertTrue(s['complete'])
        r['expected_titles']=['營業費用']
        self.assertEqual(score(r,[c])['score'],0)
        r['expected_titles']=['IFRS 17保險合約'];c['chunk']['sub_section']='三、IFRS 9保險合約'
        self.assertEqual(score(r,[c])['score'],0)
        c['chunk']['sub_section']='三、IFRS 17保險合約'
        self.assertEqual(score(r,[c])['score'],10)
    def test_first_sibling_only_and_no_rank_penalty_from_duplicates(self):
        entries=[candidate('a',[A],parent='p'),candidate('aa',[A],parent='p'),candidate('b',[B],parent='q')]
        s=score(row(),entries)
        self.assertEqual(s['score'],10)
        self.assertEqual(len(s['top20']),2)
        self.assertEqual(s['top20'][1]['effective_rank'],2)
        self.assertEqual(s['top20'][1]['original_rank'],3)
        s=score(row(),[candidate('a',parent='p'),candidate('b',[A,B],parent='p')])
        self.assertEqual(s['score'],0)
    def test_multiple_pages_and_titles_report_missing(self):
        r=row();r['expected_pages'].append({'report_year':2024,'stock_code':'2330','page':51})
        s=score(r,[candidate('a',[A])])
        self.assertEqual(s['page_coverage'],'1/2')
        self.assertEqual(s['missing_pages'],['2024_2330_P51'])
        self.assertEqual(s['missing_titles'],[B])
    def test_year_or_filter(self):
        sig={'fields':[('metadata.years','metadata'),('metadata.stock_code','metadata')]}
        self.assertEqual(build_filters(sig,None,[2023,2024]),{'$or':[{'years':{'$contains':2023}},{'years':{'$contains':2024}}]})
        self.assertEqual(build_filters(sig,None,2024),{'years':{'$contains':2024}})
        for value in ([True],[],[2024,'2023']):
            with self.assertRaises(ValueError):build_filters(sig,None,value)
    def test_disabled_blocks_experiment_but_not_query(self):
        with patch('Code_2.config.evaluation.EvaluationSettings',return_value=type('C',(),{'enabled':False})()):
            with self.assertRaisesRegex(ValueError,'停用'):validate_task({'action':'evaluate'},Settings())
        query=dict(action='query',question='問題',backend='bge',collection='financial_'+'a'*24,mode='retrieve',retrieve_k=50,evidence_k=10)
        self.assertEqual(validate_task(query,Settings())['action'],'query')
    def test_fake_run_no_reference_leak_exports_questions_as_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            settings=replace(Settings(),project_root=Path(temp))
            data=dict(action='evaluate',workbook_base64=upload([values(),values('2')]),filename='測試.xlsx',sheet='題目',ids=['1','2'],
                backend='bge',collection='financial_'+'a'*24,mode='retrieve',generate_charts=True)
            index={'backend':'bge','collection':data['collection'],'doc_ids':['2024Q4_2330_Financial_Report'],'signature':{}}
            calls=[]
            def fake(question,settings,**kw):
                calls.append((question,kw['report_year'],kw['stock_code']))
                c=candidate('a',[A,B])['chunk']
                payload={'original_chunk':c,'embedding_text':'證據'}
                e={'chunk_id':'a','text':'證據','retrieval_rank':1,'matched_chunk_ids':['a']}
                kw['observer']('retrieval',{'elapsed_seconds':.1,'parent_expansion_seconds':.01,'rows':[{'payload':payload}], 'sources':[e]})
                return {'status':'retrieved','retrieved_evidence':[e]}
            result=run_batch(data,settings,QASettings(),ask_function=fake,index=index,token_counter=lambda xs:sum(map(len,xs)))
            self.assertEqual(calls,[('問題',[2023,2024],'2330')]*2)
            self.assertEqual(result['summary']['mean_score'],10)
            self.assertEqual(result['summary']['mean_raw_score'],10)
            self.assertEqual(result['raw_curves']['returned']['points'][-1]['mean_score'],10)
            self.assertEqual(result['curves']['returned']['points'][-1]['mean_score'],10)
            self.assertEqual(result['export_status'],'saved')
            target=Path(result['output_dir'])
            self.assertTrue((target/'answer.md').is_file())
            self.assertIn('平均得分：10', (target/'answer.md').read_text(encoding='utf-8'))
            self.assertTrue((target/'result.json').is_file())
            with zipfile.ZipFile(target/'results.xlsx') as z:
                workbook=z.read('xl/workbook.xml').decode()
                self.assertIn('檢索TopK曲線',workbook)
                self.assertIn('檢索五筆增量',workbook)
                self.assertIn('檢索逐題對照',workbook)
                overview=z.read('xl/worksheets/sheet1.xml').decode()
                self.assertIn('建議圖型',overview)
                self.assertIn('主要表達',overview)
                xml=z.read('xl/worksheets/sheet2.xml').decode()
                self.assertIn('r="B1"',xml);self.assertIn('r="C1"',xml)
                detail=z.read('xl/worksheets/sheet5.xml').decode();self.assertIn('>1</t>',detail);self.assertIn('>2</t>',detail)
                self.assertNotIn('參考答案不得進模型',xml)
            self.assertEqual(report_path(settings,target.name,'results.xlsx'),target/'results.xlsx')
            with patch('Code_2.functions.experiments.eval_run.build_curves') as curves:
                plain=run_batch({**data,'generate_charts':False},replace(settings,export_enabled=False),
                    QASettings(),ask_function=fake,index=index,token_counter=lambda xs:0)
                curves.assert_not_called()
                self.assertEqual(plain['curves'],{})
                self.assertEqual(plain['raw_curves'],{})
                self.assertEqual(plain['summary']['mean_raw_score'],10)

    def test_no_export_has_no_output_and_failure_stops_following_questions(self):
        with tempfile.TemporaryDirectory() as temp:
            settings=replace(Settings(),project_root=Path(temp),export_enabled=False)
            data=dict(workbook_base64=upload([values(),values('2')]),filename='測試.xlsx',ids=['1','2'],backend='bge',collection='x',mode='retrieve')
            index={'backend':'bge','collection':'x','doc_ids':['2024Q4_2330_Financial_Report'],'signature':{}}
            result=run_batch(data,settings,QASettings(),ask_function=lambda *a,**k:{'status':'failed','error':'fake'},index=index,token_counter=lambda xs:0)
            self.assertEqual([r['status'] for r in result['rows']],['failed','not_run'])
            self.assertFalse(settings.response_dir.exists())
if __name__=='__main__':unittest.main()
