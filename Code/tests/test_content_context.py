"""第三→第四→第五及QA證據串接；合成來源，不呼叫模型或寫Output。"""
import unittest
from copy import deepcopy
from test_hierarchical_modes import run
from functions.content_context import content_body, description_without_years, context_prefix
from functions.chunking.chunks import validate_chunk_document
from Code.functions.embedding.prepare import prepare_document, validate_document
from Code.functions.embedding.load_prepared import validate_prepared
from Code_2.functions.qa.pipeline import evidence_rows


TABLE = '<table><tr><th>金額</th></tr><tr><td>100</td></tr></table>\n'


class ContentContextTests(unittest.TestCase):
    def prepared(self, doc):
        result = prepare_document(doc, input_sha256='a'*64)
        validate_prepared(result)
        return result

    def test_table_direction_supplies_years_and_description_once(self):
        doc = run('## 112及111年度各產品金額如下：\n'+TABLE, 'parent_child').document
        chunk = doc['chunks'][0]
        self.assertEqual(doc['schema_version'], 'financial-chunks/5.0')
        self.assertEqual(chunk['years'], [2022, 2023, 2025])
        self.assertEqual(chunk['year_sources'][0]['source'], 'preceding_table_direction')
        self.assertNotIn('年度：', chunk['content_prefix'])
        self.assertNotIn('股票代號：', chunk['content_prefix'])
        self.assertNotIn('Main_Section：', chunk['content_prefix'])
        self.assertIn('各產品金額如下：', chunk['content'])
        self.assertNotIn('112及111年度', chunk['content'])
        self.assertEqual(chunk['table_context'], '112及111年度各產品金額如下：')
        self.assertEqual(content_body(chunk), TABLE)
        text = self.prepared(doc)['chunks'][0]['embedding_text']
        self.assertEqual(text.count('各產品金額如下：'), 1)
        self.assertNotIn('112及111年度', text)
        self.assertNotIn('股票代號：2330', text)
        self.assertNotIn('Main_Section：', text)
        self.assertEqual(self.prepared(doc)['chunks'][0]['metadata']['years'],[2022,2023,2025])

    def test_pure_year_does_not_replace_description_and_header_years_win(self):
        body = '## 金額說明如下：\n## 112年度\n'+TABLE
        chunk = run(body, 'parent_child').document['chunks'][0]
        self.assertEqual(chunk['years'], [2023, 2025])
        self.assertIn('金額說明如下：', chunk['content_prefix'])
        body = '## 112及111年度各產品金額如下：\n'+TABLE.replace('金額', '114年度')
        chunk = run(body, 'parent_child').document['chunks'][0]
        self.assertEqual(chunk['years'], [2025])
        self.assertIn('各產品金額如下：', chunk['content_prefix'])
        self.assertIn('114年度', content_body(chunk))

    def test_strip_only_year_fragments_preserving_financial_values_and_durations(self):
        cases = {
            '民國一一四年度及一一三年度營收為$2,025，年增4.375%。': '營收為$2,025，年增4.375%。',
            '１１２ 及 １１１ 年度金額１，２００千元。': '金額１，２００千元。',
            '耐用年限10年，股票代號2330，金額112。': '耐用年限10年，股票代號2330，金額112。',
            '112年12月31日餘額如下：': '12月31日餘額如下：',
            '114.12.31餘額如下：': '12.31餘額如下：',
            '112及111年度：': '',
            '112年及111年各產品營收如下：': '各產品營收如下：',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(description_without_years(text), expected)

    def test_text_description_uses_same_format_without_changing_years_or_source(self):
        doc = run('## 112及111年度相關說明\n原文內容。\n', 'parent_child').document
        chunk = doc['chunks'][0]
        self.assertEqual(chunk['years'], [2025])
        self.assertNotIn('年度：', chunk['content_prefix'])
        self.assertNotIn('股票代號：', chunk['content_prefix'])
        self.assertEqual(chunk['doc_id'],'2025Q4_2330_Financial_Report')
        self.assertIn('相關說明', chunk['content_prefix'])
        self.assertEqual(chunk['directions'][0]['text'], '112及111年度相關說明')
        self.assertEqual(content_body(chunk), '原文內容。\n')
        self.prepared(doc)

    def test_previous_41_prefix_still_valid_without_rewriting_old_outputs(self):
        doc = run('## 112及111年度相關說明\n原文內容。\n', 'parent_child').document
        doc['schema_version']='financial-chunks/4.1'
        doc.pop('embedding_context_modes')
        doc['rule_version']='hierarchical-semantic-chunks/4.1-context'
        for chunk in doc['chunks'] + doc['parents']:
            for name in ('node_type','parent_relation','heading_parent_id'):
                chunk.pop(name)
            body = content_body(chunk)
            chunk.pop('embedding_context_mode')
            chunk.pop('content_prefix_format')
            chunk['content_prefix'] = context_prefix(chunk, remove_years=False, include_identity=True)
            chunk['content'] = chunk['content_prefix'] + body
        validate_chunk_document(doc)
        self.prepared(doc)

    def test_prose_heading_and_direction_and_direct_parent_return(self):
        body = '## (一)退休金\n## 風險說明如下：\n'+'甲'*400+'\n\n'+'乙'*400+'\n'
        doc = run(body, 'parent_child').document
        chunk, parent = doc['chunks'][0], doc['parents'][0]
        self.assertIn('退休金', chunk['content_prefix'])
        self.assertIn('風險說明如下：', chunk['content_prefix'])
        self.assertEqual(''.join(content_body(c) for c in doc['chunks']), content_body(parent))
        self.assertEqual(chunk['body_char_count'], 400)
        self.prepared(doc)
        row = {'chunk_id': chunk['chunk_id'], 'distance': 0.2,
               'metadata': {'_sys_chunk_id':chunk['chunk_id'], '_sys_doc_id':chunk['doc_id'],
                            '_sys_input_sha256':'a'*64},
               'payload': {'schema_version':'financial-vector-payload/1.0', 'original_chunk':chunk,
                           'original_parent':parent, 'input_sha256':'a'*64}}
        evidence = evidence_rows([row])[0]
        self.assertNotIn('股票代號：2330', evidence['text'])
        self.assertNotIn('Main_Section：', evidence['text'])
        self.assertIn('乙'*400, evidence['text'])

    def test_empty_context_has_no_generated_blank_line(self):
        chunk={'doc_id':'2025Q4_2330_Financial_Report','years':[2025],
               'main_section':'大標','sub_section':'','note_title':[],
               'content_type':'text','directions':[],'content':'原文2025年2330。'}
        self.assertEqual(context_prefix(chunk),'')
        from functions.content_context import add_context
        add_context(chunk)
        self.assertEqual(content_body(chunk),'原文2025年2330。')
        self.assertEqual(chunk['content'],'原文2025年2330。')

    def test_corrupt_prefix_rejected_by_both_contracts(self):
        doc = run('甲。\n', 'parent_child').document
        changed = deepcopy(doc)
        changed['chunks'][0]['content'] = '錯誤首行' + changed['chunks'][0]['content']
        for validator in (validate_chunk_document, validate_document):
            with self.assertRaises(ValueError):
                validator(changed)

    def test_original_mode_preserves_content_and_source_spans(self):
        result = run('## 說明如下：\n甲。\n')
        doc = result.document
        self.assertEqual(doc['schema_version'], 'financial-chunks/5.0')
        self.assertIn('content_prefix', doc['chunks'][0])
        self.assertEqual(content_body(doc['chunks'][0]), '甲。\n')
        self.prepared(doc)


if __name__ == '__main__':
    unittest.main()
