"""新切法、兩種父子關係與檢索開關；不呼叫外部模型。"""
import unittest
from copy import deepcopy
from test_hierarchical_modes import run
from functions.content_context import content_body
from functions.chunking.chunks import validate_chunk_document
from Code.functions.embedding.prepare import prepare_document,validate_document
from Code.functions.embedding.load_prepared import validate_prepared
from Code_2.functions.qa.pipeline import evidence_rows

T1='<table><tr><th>112年度</th></tr><tr><td>100</td></tr></table>\n'
T2='<table><tr><th>金額</th></tr><tr><td>(20)</td></tr></table>\n'


def rows(doc):
    parents={p['chunk_id']:p for p in doc['parents']}
    return [{'chunk_id':c['chunk_id'],'distance':0.1,
             'metadata':{'_sys_chunk_id':c['chunk_id'],'_sys_doc_id':c['doc_id'],'_sys_input_sha256':'a'*64},
             'payload':{'schema_version':'financial-vector-payload/1.0','input_sha256':'a'*64,
                        'original_chunk':c,'original_parent':parents.get(c['parent_id']),
                        'original_heading_parent':parents.get(c['heading_parent_id'])}} for c in doc['chunks']]


class ParentChildV5Tests(unittest.TestCase):
    def check(self,doc):
        validate_chunk_document(doc)
        prepared=prepare_document(doc,input_sha256='a'*64)
        validate_prepared(prepared)
        self.assertEqual(len(prepared['chunks']),len(doc['chunks']))
        self.assertFalse(any(p['node_type']=='chunk' for p in doc['parents']))
        return doc

    def test_adjacent_contents_merge_under_limit(self):
        doc=self.check(run('甲'*200+'\n\n'+'乙'*300+'\n',
                           'parent_child',explicit_content_boundaries=True).document)
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[500])
        self.assertEqual(doc['parents'],[])
        self.assertIn('甲'*200+'\n'+'乙'*300,content_body(doc['chunks'][0]))
        self.assertEqual(doc['rule_version'],'bounded-parent-child/5.7')

    def test_adjacent_contents_split_after_merge_and_return_whole_parent(self):
        doc=self.check(run('甲'*300+'\n\n'+'乙'*300+'\n\n'+'丙'*400+'\n',
                           'parent_child',explicit_content_boundaries=True).document)
        parent=doc['parents'][0]
        self.assertEqual(parent['node_type'],'content_parent')
        self.assertEqual(parent['body_char_count'],1000)
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[500,500])
        for row in rows(doc):
            evidence=evidence_rows([row])
            self.assertEqual(len(evidence),1)
            self.assertEqual(evidence[0]['chunk_id'],parent['chunk_id'])
            self.assertIn('甲'*300,evidence[0]['text'])
            self.assertIn('丙'*400,evidence[0]['text'])

    def test_direction_and_year_do_not_stop_merge(self):
        body='甲'*200+'\n## 民國114年度\n乙文。\n## 說明如下：\n丙文。\n'
        doc=self.check(run(body,'parent_child').document)
        self.assertEqual(len(doc['chunks']),1)
        self.assertIn('甲'*200,content_body(doc['chunks'][0]))
        self.assertIn('乙文。',content_body(doc['chunks'][0]))
        self.assertIn('丙文。',content_body(doc['chunks'][0]))
        self.assertTrue(doc['chunks'][0]['directions'])
        self.assertTrue(doc['chunks'][0]['table_year'])

    def test_new_heading_table_and_list_stop_content_merge(self):
        body='甲文。\n\n乙文。\n## (一)子標題\n丙文。\n'+T1+'丁文。\n### 1.編碼\n戊文。\n'
        doc=self.check(run(body,'parent_child',explicit_content_boundaries=True).document)
        self.assertEqual(len(doc['chunks']),5)
        self.assertIn('甲文。\n乙文。',content_body(doc['chunks'][0]))
        self.assertEqual(content_body(doc['chunks'][1]),'丙文。\n')
        self.assertEqual(doc['chunks'][2]['content_type'],'table')
        self.assertEqual(content_body(doc['chunks'][3]),'丁文。\n')
        self.assertIn('1.編碼',content_body(doc['chunks'][4]))
        self.assertNotIn('丁文。',content_body(doc['chunks'][4]))

    def test_hard_count_and_configurable_limit(self):
        doc=self.check(run('甲'*1000+'\n','parent_child').document)
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[500,500])
        self.assertEqual(doc['parents'][0]['node_type'],'content_parent')
        self.assertEqual([c['parent_relation'] for c in doc['chunks']],['content','content'])
        changed=run('甲'*1000+'\n','parent_child',recursive_threshold=300).document
        self.assertEqual([c['body_char_count'] for c in changed['chunks']],[250]*4)

    def test_blank_line_precedes_chinese_stop_and_english_period_is_ignored(self):
        doc=self.check(run('甲'*505+'。'+'甲'*4+'\n\n'+'乙'*490+'\n','parent_child').document)
        self.assertEqual(doc['chunks'][0]['body_char_count'],510)
        doc=run('甲'*510+'。'+'乙'*489+'\n','parent_child').document
        self.assertEqual(doc['chunks'][0]['body_char_count'],511)
        doc=run('甲'*490+'.'+'乙'*509+'\n','parent_child').document
        self.assertEqual(doc['chunks'][0]['body_char_count'],500)
        doc=run('甲'*900+'\n\n'+'乙'*100+'\n','parent_child').document
        self.assertTrue(all(c['body_char_count']<=700 for c in doc['chunks']))

    def test_list_group_keeps_all_items_over_limit_and_strips_marks(self):
        body='前段。\n### 1.項目\n'+'甲'*800+'\n### 2.項目\n乙。\n'
        doc=self.check(run(body,'parent_child').document)
        self.assertEqual(len(doc['chunks']),2)
        self.assertEqual(content_body(doc['chunks'][0]),'前段。\n')
        self.assertNotIn('###',content_body(doc['chunks'][1]))
        self.assertIn('2.項目',content_body(doc['chunks'][1]))
        self.assertGreater(doc['chunks'][1]['body_char_count'],700)
        self.assertEqual(doc['issues'][0]['status'],'list_group_exceeds_limit_by_design')
        self.assertTrue(doc['removed_markup_spans'])

    def test_table_is_independent_and_heading_parent_can_be_mixed(self):
        doc=self.check(run('前文。\n'+T1+'後文。\n','parent_child').document)
        self.assertEqual([c['content_type'] for c in doc['chunks']],['text','table','text'])
        self.assertEqual(content_body(doc['chunks'][1]),T1)
        heading=[p for p in doc['parents'] if p['node_type']=='heading_parent']
        self.assertEqual(len(heading),1)
        self.assertEqual(heading[0]['content_type'],'mixed')

    def test_cross_page_table_child_always_returns_complete_parent(self):
        body=T1+'接次頁\n<!-- Page: 2330_2025_P16 -->\n承前頁\n'+T2
        doc=self.check(run(body,'parent_child').document)
        self.assertEqual([c['page'] for c in doc['chunks']],[[15],[16]])
        self.assertTrue(all(c['parent_relation']=='table' for c in doc['chunks']))
        self.assertTrue(all(c['years']==[2023,2025] for c in doc['chunks']))
        evidence=evidence_rows(rows(doc))
        self.assertEqual(len(evidence),1)
        self.assertIn('(20)',evidence[0]['text'])
        self.assertIn('100',evidence[0]['text'])
        self.assertNotIn('<!-- Page:',content_body(doc['parents'][0]))

    def test_heading_group_ignores_leaf_but_not_subsection_or_source_identity(self):
        body='## (一)甲\n甲文。\n## (二)乙\n乙文。\n## 二、另一節\n## (一)甲\n另一段。\n'
        doc=self.check(run(body,'parent_child').document)
        a,b,c=doc['chunks']
        self.assertEqual(a['heading_parent_id'],b['heading_parent_id'])
        self.assertIsNotNone(a['heading_parent_id'])
        self.assertIsNone(c['heading_parent_id'])
        self.assertEqual(len(evidence_rows(rows(doc))),3)
        expanded=evidence_rows(rows(doc),include_heading_parent=True)
        self.assertEqual(sum(s['parent_relation']=='heading' for s in expanded),1)

    def test_mandatory_parent_and_optional_heading_are_independent(self):
        body='## (一)甲\n'+'甲'*1000+'\n## (二)乙\n乙文。\n'
        doc=self.check(run(body,'parent_child').document)
        selected=rows(doc)[:2]
        regular=evidence_rows(selected)
        expanded=evidence_rows(selected,include_heading_parent=True)
        self.assertEqual(len(regular),1)
        self.assertEqual(regular[0]['parent_relation'],'content')
        self.assertEqual({s['parent_relation'] for s in expanded},{'content','heading'})
        self.assertEqual(len(expanded),2)
        self.assertNotIn('include_heading_parent',doc['chunking'])
        bad=deepcopy(selected)
        bad[0]['payload']['original_heading_parent']=None
        with self.assertRaises(ValueError):
            evidence_rows(bad,include_heading_parent=True)

    def test_bad_relations_rejected_before_embedding(self):
        doc=run('甲'*1000+'\n','parent_child').document
        doc['chunks'][0]['parent_relation']='heading'
        for validator in (validate_chunk_document,validate_document):
            with self.assertRaises(ValueError):
                validator(doc)

    def test_unicode_blank_and_entities_are_safe_boundaries(self):
        doc=self.check(run('甲'*510+'\r\n\u00a0\r\n'+'乙'*490+'\n','parent_child').document)
        self.assertEqual(doc['chunks'][0]['body_char_count'],510)
        doc=self.check(run('&amp;'*1000+'\n','parent_child').document)
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[500,500])
        self.assertTrue(all(content_body(c).count('&amp;')==500 for c in doc['chunks']))

    def test_title_parent_not_created_across_repeated_heading_occurrences(self):
        body='## 一、政策\n甲文。\n## 一、政策\n乙文。\n'
        doc=self.check(run(body,'parent_child').document)
        self.assertTrue(all(c['heading_parent_id'] is None for c in doc['chunks']))

    def test_literal_markers_in_code_and_html_not_removed(self):
        doc=self.check(run('```text\n### literal code\n```\n'+T1.replace('100','### literal cell'),'parent_child').document)
        self.assertIn('### literal code',doc['chunks'][0]['content'])
        self.assertIn('### literal cell',doc['chunks'][1]['content'])


if __name__=='__main__':
    unittest.main()
