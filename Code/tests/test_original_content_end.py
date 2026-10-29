"""original確認規則：content_end軟門檻、hd2邊界及共用表格契約。"""
import unittest
from test_hierarchical_modes import run
from functions.content_context import content_body
from Code.functions.embedding.prepare import prepare_document
from Code.functions.embedding.load_prepared import validate_prepared
from Code_2.functions.qa.pipeline import evidence_rows


class OriginalContentEndTests(unittest.TestCase):
    def check(self,doc):
        self.assertEqual(doc['schema_version'],'financial-chunks/5.0')
        self.assertEqual(doc['rule_version'],'content-end-original/1.5')
        self.assertEqual(doc['chunking']['mode'],'original')
        validate_prepared(prepare_document(doc,input_sha256='a'*64))
        for c in doc['chunks']+doc['parents']:
            self.assertNotIn('Main_Section：',c['content_prefix'])
            self.assertNotIn('年度：',c['content_prefix'])
        self.assertTrue(all(c['heading_parent_id'] is None for c in doc['chunks']+doc['parents']))
        self.assertTrue(all(p['node_type']!='heading_parent' for p in doc['parents']))
        self.assertTrue(all(p['node_type']=='table_parent' or p['cut_reason']=='body_list_group' for p in doc['parents']))
        return doc
    def test_accumulate_past_threshold_then_content_end(self):
        doc=self.check(run(('甲'*400+'\n\n')*3,explicit_content_boundaries=True).document)
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[800,400])
        self.assertEqual(doc['parents'],[])
        self.assertTrue(all(c['parent_id'] is None for c in doc['chunks']))
        self.assertFalse(any(p['node_type']=='content_parent' for p in doc['parents']))
    def test_single_long_content_stays_whole_and_limit_is_configurable(self):
        doc=self.check(run('甲'*1000+'\n').document)
        self.assertEqual(len(doc['chunks']),1)
        self.assertEqual(doc['chunks'][0]['body_char_count'],1000)
        self.assertIsNone(doc['chunks'][0]['parent_id'])
        doc=run(('甲'*400+'\n\n')*3,explicit_content_boundaries=True,recursive_threshold=300).document
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[400]*3)
    def test_hd3_and_hd4_do_not_cut_and_all_paths_retained(self):
        body='## (一)收入\n## 1.甲項\n'+'甲'*400+'\n## 2.乙項\n'+'乙'*400+'\n'
        doc=self.check(run(body).document)
        self.assertEqual(len(doc['chunks']),1)
        c=doc['chunks'][0]
        self.assertEqual(c['body_char_count'],800)
        self.assertIn('甲項',c['content_prefix'])
        self.assertIn('乙項',c['content_prefix'])
        self.assertNotIn('<hd',content_body(c))
    def test_hd2_always_finishes_underfilled_chunk(self):
        doc=self.check(run('甲'*400+'\n## 二、應收帳款\n'+'乙'*400+'\n').document)
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[400,400])
        self.assertNotEqual(doc['chunks'][0]['sub_section'],doc['chunks'][1]['sub_section'])
    def test_tables_independent_and_cross_page_parent_recalled(self):
        table='<table><tr><td>(123)</td></tr></table>\n'
        body='前文。\n'+table+'接次頁\n<!-- Page: 2330_2025_P16 -->\n承前頁\n'+table+'後文。\n'
        doc=self.check(run(body).document)
        self.assertEqual([c['content_type'] for c in doc['chunks']],['text','table','table','text'])
        tables=[c for c in doc['chunks'] if c['parent_relation']=='table']
        parent=next(p for p in doc['parents'] if p['node_type']=='table_parent')
        c=tables[0]
        row={'chunk_id':c['chunk_id'],'distance':.1,'metadata':{'_sys_chunk_id':c['chunk_id'],'_sys_doc_id':c['doc_id'],'_sys_input_sha256':'a'*64},'payload':{'schema_version':'financial-vector-payload/1.0','original_chunk':c,'original_parent':parent,'input_sha256':'a'*64}}
        evidence=evidence_rows([row])[0]
        self.assertEqual(evidence['page'],[15,16])
        self.assertEqual(evidence['text'].count('(123)'),2)
    def test_list_whole_and_blank_lines_removed_last(self):
        doc=self.check(run('前文。\n### 1.項目\n'+'甲'*800+'\n\n### 2.項目\n乙。\n').document)
        self.assertEqual(len(doc['chunks']),2)
        self.assertGreater(doc['chunks'][1]['body_char_count'],700)
        self.assertNotIn('###',content_body(doc['chunks'][1]))
        self.assertNotIn('\n\n',content_body(doc['chunks'][1]))


if __name__=='__main__':unittest.main()
