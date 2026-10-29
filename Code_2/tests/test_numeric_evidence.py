"""必要數字評分：合成資料，不呼叫API或使用者索引。"""
import base64
import json
import unittest
from Code_2.functions.experiments.eval_scoring import score
from Code_2.functions.experiments.numeric_evidence import missing_numbers,parse_targets
from Code_2.functions.experiments.eval_workbook import read_upload,write_xlsx


def question():
    return {'stock_code':'2330','filter_years':[2023,2024],
            'expected_titles':['一、營業收入'],'expected_pages':[],
            'numeric_targets':[
                {'year':2023,'title':'營業收入','numbers':['934,768,625']},
                {'year':2024,'title':'營業收入','numbers':['1,476,890,566']}]}


def candidate(cid,text,years=(2023,2024),stock='2330',title='營業收入',parent=None):
    return {'chunk':{'chunk_id':cid,'doc_id':f'2025Q4_{stock}_Financial_Report',
                     'years':list(years),'note_title':[title],'page':[49,50],
                     'parent_id':parent},'text':text}


class NumericEvidenceTests(unittest.TestCase):
    def test_formatting_boundaries_signs_and_percent(self):
        self.assertEqual(missing_numbers(['1,476,890,566','-1.25','93%'],
                         '<td>1, 476, 890,566</td> −1.25 93 %'),[])
        for expected,text in [('100','1000'),('1.2','12'),('100','-100'),
                              ('93%','93'),('100','100%'),('-100','100')]:
            self.assertEqual(missing_numbers([expected],text),[expected])
        self.assertEqual(missing_numbers(['-100'],'(100)'),[])
        self.assertEqual(missing_numbers(['259327332','62695'],'259,327 , 332；62 , 695'),[])
        self.assertEqual(missing_numbers(['1000'],'<td>1</td><td>000</td>'),['1000'])

    def test_correct_title_but_wrong_numbers_is_zero(self):
        result=score(question(),[candidate('c1','123')],retrieve_k=50)
        self.assertEqual(result['raw_score'],0)
        self.assertFalse(result['complete'])

    def test_numbers_ignore_year_title_and_stock_metadata(self):
        q=question()
        entries=[candidate('a','934768625',years=(2024,)),
                 candidate('b','1476890566',stock='2317'),
                 candidate('c','1476890566',title='其他科目')]
        self.assertEqual(score(q,entries,retrieve_k=50)['raw_score'],10)

    def test_each_year_can_be_in_different_chunk(self):
        result=score(question(),[candidate('a','934768625',years=(2023,)),
                                 candidate('b','1476890566',years=(2024,))],retrieve_k=50)
        self.assertEqual(result['raw_score'],10)
        self.assertEqual(result['score'],10)
        self.assertTrue(result['complete'])

    def test_one_year_only_is_half(self):
        result=score(question(),[candidate('a','934768625',years=(2023,))],retrieve_k=50)
        self.assertEqual(result['raw_score'],5)
        self.assertEqual(result['target_coverage'],'1/2')

    def test_numbers_for_same_target_pool_across_eligible_candidates(self):
        q=question();q['numeric_targets'][0]['numbers'].append('69,482,307')
        result=score(q,[candidate('a','934768625'),candidate('b','69482307')],retrieve_k=50)
        self.assertEqual(result['raw_score'],5)
        self.assertEqual(result['target_hits']['2023｜營業收入'],2)
        hits=result['number_hits']['2023｜營業收入']
        self.assertEqual(hits['934,768,625']['chunk_id'],'a')
        self.assertEqual(hits['69,482,307']['chunk_id'],'b')

    def test_pool_accepts_numbers_despite_different_metadata(self):
        q=question();q['numeric_targets'][0]['numbers'].append('69,482,307')
        first=candidate('a','934768625',years=(2023,))
        for second in [candidate('b','69482307',years=(2024,)),
                       candidate('b','69482307',stock='2317'),
                       candidate('b','69482307',title='其他科目')]:
            self.assertEqual(score(q,[first,second],retrieve_k=50)['raw_score'],5)

    def test_duplicate_number_does_not_complete_target_or_change_first_rank(self):
        q=question();q['numeric_targets'][0]['numbers'].append('69,482,307')
        result=score(q,[candidate('a','934768625'),candidate('repeat','934768625'),
                        candidate('b','69482307')],retrieve_k=50)
        self.assertEqual(result['raw_score'],5)
        self.assertEqual(result['target_hits']['2023｜營業收入'],3)
        self.assertEqual(result['number_hits']['2023｜營業收入']['934,768,625']['effective_rank'],1)

    def test_sibling_texts_can_supply_numbers_without_duplicate_rank(self):
        q=question();q['numeric_targets'][0]['numbers'].append('69,482,307')
        result=score(q,[candidate('a','934768625',parent='p'),
                        candidate('b','69482307',parent='p')],retrieve_k=50)
        self.assertEqual(result['raw_score'],5)
        self.assertEqual(result['target_hits']['2023｜營業收入'],1)
        self.assertEqual(len(result['top20']),1)

    def test_parent_text_and_duplicate_fact(self):
        entries=[candidate('parent','934768625 1476890566'),
                 candidate('duplicate','934768625 1476890566')]
        result=score(question(),entries,retrieve_k=50)
        self.assertEqual(result['raw_score'],10)
        self.assertEqual(len(result['contributions']),2)

    def test_numbers_define_targets_without_expected_headings(self):
        q=question();q['expected_titles']=[];q['filter_years']=[]
        result=score(q,[candidate('a','934768625 1476890566',years=(),title='其他')],retrieve_k=50)
        self.assertEqual(result['raw_score'],10)
        self.assertTrue(result['complete'])
        self.assertEqual(result['scoring_rule'],'numbers-only/1.0')
        self.assertFalse(result['numeric_metadata_gate'])

    def test_pending_annotation_not_counted_even_when_numbers_match(self):
        q=question();q['Required_Numbers_Status']='pending';q['Required_Numbers_Note']='原表欄位待核對'
        result=score(q,[candidate('a','934768625 1476890566')],retrieve_k=50)
        self.assertIsNone(result['raw_score'])
        self.assertIsNone(result['score'])
        self.assertFalse(result['complete'])
        self.assertIn('原表欄位待核對',result['scoring_note'])

    def test_legacy_is_explicit(self):
        q=question();q.pop('numeric_targets')
        result=score(q,[candidate('a','no numbers')],retrieve_k=50)
        self.assertEqual(result['raw_score'],10)
        self.assertEqual(result['scoring_rule'],'year-title-dual/3.2')

    def test_excel_annotation_stays_in_reference(self):
        values=json.dumps(question()['numeric_targets'],ensure_ascii=False)
        raw=write_xlsx([('題目',[
            ['ID','Question','Years','Evidence_Note_Title','Required_Numbers'],
            ['1','測試問題','2023,2024','營業收入',values]])])
        row=read_upload(base64.b64encode(raw).decode(),'test.xlsx')['rows'][0]
        self.assertEqual(row['errors'],[])
        self.assertEqual(row['numeric_targets'],question()['numeric_targets'])

    def test_invalid_annotation_fails(self):
        for value in ('bad','[]','[{"year":2024}]'):
            with self.assertRaises(ValueError):parse_targets(value)


if __name__=='__main__':unittest.main()
