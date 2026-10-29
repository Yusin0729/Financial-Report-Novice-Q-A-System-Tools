"""新版兩模式與語意完整性；只用合成資料／假向量，不呼叫外部模型。"""
import hashlib
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.chunking import ChunkSettings
from functions.chunking.chunks import chunk_tagged
from functions.content_context import content_body
from functions.markdown_processing.comment_tagging import tag_comments
from schemas import TaggingMetadata
from Code_2.functions.embedding.prepare import prepare_document
from Code_2.functions.embedding.load_prepared import validate_prepared
from Code_2.functions.qa.pipeline import evidence_rows

PAGE = '<!-- Page: 2330_2025_P15 -->\n'
TABLE = '<table><tr><th>114及113年度</th></tr><tr><td>$(1,234.50)</td></tr></table>\n'


def run(body, mode='original', *, explicit_content_boundaries=False, **params):
    raw = '<note>\n' + PAGE + '## 一、會計政策\n' + body
    text = tag_comments(raw, None, TaggingMetadata(report_year='2025', stock_code='2330')).markdown
    if explicit_content_boundaries:
        # 第四階段單元測試明確提供content邊界，不依賴第三階段是否按空行標記。
        text = re.sub(r'(<content_start>\n)(.*?)(</content_end>)',
            lambda m:m[1]+re.sub(r'\n\n', '\n</content_end>\n\n<content_start>\n', m[2])+m[3], text, flags=re.S)
    result = chunk_tagged(text, identity=('2025', '2330'), source_sha256=hashlib.sha256(text.encode()).hexdigest(),
                          config=replace(ChunkSettings(), mode=mode, **params))
    return result


class HierarchicalTests(unittest.TestCase):
    def test_stage_three_content_is_split_by_new_stage_four_limit(self):
        doc = run('甲'*400+'\n\n'+'乙'*400+'\n', 'parent_child').document
        self.assertEqual([c['body_char_count'] for c in doc['chunks']], [400,400])
        self.assertIn('甲'*400+'\n'+'乙'*400,doc['parents'][0]['content'])

    def test_small_heading_is_one_normal_chunk_without_parent(self):
        result = run('## (一) 存貨\n' + '甲'*400 + '\n')
        self.assertEqual(len(result.document['chunks']), 1)
        self.assertEqual(result.document['parents'], [])
        self.assertNotIn('<hd', result.document['chunks'][0]['content'])

    def test_original_accumulates_across_lower_headings(self):
        body = '## (一) 存貨\n' + ''.join('## '+str(i)+'. 項目\n'+char*n+'\n'
               for i, char, n in [(1,'甲',400),(2,'乙',350),(3,'丙',250)])
        doc = run(body).document
        self.assertEqual([c['body_char_count'] for c in doc['chunks']], [750,250])
        self.assertFalse(any(p['node_type']=='content_parent' for p in doc['parents']))

    def test_original_ignores_hd3_under_same_hd2(self):
        body = '## (一) 收入\n' + ('甲'*400+'\n\n')*3 + '## (二) 存貨\n乙。\n'
        doc = run(body, explicit_content_boundaries=True).document
        self.assertEqual([c['body_char_count'] for c in doc['chunks']], [800,402])
        self.assertNotIn('乙',content_body(doc['chunks'][0]))
        self.assertIn('乙',content_body(doc['chunks'][1]))

    def test_small_binding_stays_normal(self):
        doc = run('## 說明如下：\n'+'甲'*200+'\n\n'+'乙'*200+'\n').document
        self.assertEqual(len(doc['chunks']), 1)
        self.assertFalse(doc['parents'])
        self.assertEqual(doc['chunks'][0]['directions'][0]['text'], '說明如下：')

    def test_original_directions_preserved_without_heading_parent(self):
        doc=run('## 說明如下：\n'+'甲'*400+'\n\n'+'乙'*400+'\n\n## 另一說明：\n丙。\n').document
        self.assertEqual(doc['parents'],[])
        self.assertEqual([c['body_char_count'] for c in doc['chunks']],[800,2])
        self.assertIn('說明如下',doc['chunks'][0]['content_prefix'])
        self.assertIn('另一說明',doc['chunks'][1]['content_prefix'])

    def test_parent_mode_merges_content_before_mandatory_split(self):
        doc = run(('甲'*600+'\n\n')*4, 'parent_child', explicit_content_boundaries=True).document
        self.assertEqual([p['body_char_count'] for p in doc['parents']], [2400])
        self.assertEqual(doc['parents'][0]['node_type'],'content_parent')
        self.assertTrue(all(c['parent_id']==doc['parents'][0]['chunk_id'] for c in doc['chunks']))
        self.assertEqual(len(doc['chunks']), 4)

    def test_indivisible_binding_over_limit_is_not_forced_apart(self):
        doc = run('## 說明如下：\n' + ('甲'*600+'\n\n')*3).document
        self.assertEqual(doc['parents'],[])
        self.assertEqual(doc['chunks'][0]['body_char_count'],1800)
        self.assertIsNone(doc['chunks'][0]['parent_id'])

    def test_full_table_over_limit_remains_exact(self):
        table = TABLE.replace('$(1,234.50)', '甲'*1800 + '$(1,234.50)')
        doc = run(table).document
        self.assertEqual(doc['parents'],[])
        self.assertEqual(content_body(doc['chunks'][0]),table)

    def test_original_tables_are_separate_from_numbered_groups(self):
        body=('## (一) 收入\n### 1. 投資\n'+'甲'*400+'\n\n'+TABLE+
              '\n### 2. 利率\n'+'乙'*400+'\n\n## (二) 租賃\n### 1. 使用權\n丙。\n')
        doc=run(body).document
        tables=[c for c in doc['chunks'] if c['content_type']=='table']
        self.assertEqual(len(tables),1)
        self.assertEqual(content_body(tables[0]),TABLE)
        self.assertTrue(all('###' not in content_body(c) for c in doc['chunks']))
        self.assertFalse(any(p['node_type']=='content_parent' for p in doc['parents']))

    def test_legacy_child_target_does_not_change_adjacent_content_merge(self):
        doc = run('甲'*200+'\n\n'+'乙'*200+'\n\n'+'丙'*100+'\n', 'parent_child', explicit_content_boundaries=True).document
        self.assertEqual([c['body_char_count'] for c in doc['chunks']], [500])
        changed = run('甲'*200+'\n\n'+'乙'*200+'\n\n'+'丙'*100+'\n', 'parent_child', explicit_content_boundaries=True, child_target=450).document
        self.assertEqual([c['body_char_count'] for c in changed['chunks']], [500])

    def test_year_and_directions_are_metadata_not_raw_body(self):
        doc = run('## 114年度\n## 所得稅組成如下：\n'+TABLE).document
        c = doc['chunks'][0]
        self.assertEqual(c['table_year'][0]['text'], '114年度')
        self.assertNotIn('<table_year>', c['content'])
        self.assertNotIn('所得稅組成如下', content_body(c))
        self.assertIn('所得稅組成如下', c['content_prefix'])
        prepared = prepare_document(doc, input_sha256='b'*64)
        validate_prepared(prepared)
        self.assertIn('所得稅組成如下', prepared['chunks'][0]['embedding_text'])

    def test_retrieval_returns_direct_parent_once_for_multiple_children(self):
        doc = run('甲'*400+'\n\n'+'乙'*400+'\n', 'parent_child').document
        parent = doc['parents'][0]
        rows = []
        for c in doc['chunks']:
            rows.append({'chunk_id': c['chunk_id'], 'distance': .1,
                'metadata': {'_sys_chunk_id': c['chunk_id'], '_sys_doc_id': c['doc_id'], '_sys_input_sha256':'b'*64},
                'payload': {'schema_version':'financial-vector-payload/1.0', 'original_chunk':c,
                            'original_parent':parent, 'input_sha256':'b'*64}})
        evidence = evidence_rows(rows)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]['chunk_id'], parent['chunk_id'])
        self.assertEqual(len(evidence[0]['matched_chunk_ids']), 2)

    def test_code_literal_list_is_not_special_group(self):
        doc = run('```\n### 1. 假條列\n```\n'+'甲'*800+'\n').document
        self.assertFalse(doc['parents'])

    def test_candidate_preparation_and_completeness(self):
        doc = run('<cannotfindtable>\n金額\n123\n</cannotfindtable>\n').document
        self.assertEqual(doc['chunks'][0]['table_completeness'], 0)
        prepared = prepare_document(doc, input_sha256='b'*64)
        self.assertIn('123', prepared['chunks'][0]['embedding_text'])

    def test_consecutive_tables_share_context_until_new_direction(self):
        body = ('## 114及113年度，第一組如下：\n'+TABLE+'\n'+TABLE+
                '\n## 114及113年度，第二組如下：\n'+TABLE)
        doc = run(body).document
        tables = [c for c in doc['chunks'] if c['table_ids']]
        self.assertEqual(len(tables),3)
        self.assertTrue(all(len(c['table_ids'])==1 for c in tables))
        self.assertTrue(all(content_body(c)==TABLE for c in tables))
        self.assertIn('第一組',tables[0]['table_context'])
        self.assertIn('第一組',tables[1]['table_context'])
        self.assertIn('第二組',tables[2]['table_context'])
        self.assertEqual(len({key for c in tables for key in c['table_ids']}), 3)

    def test_source_spans_reconstruct_body_without_loss_or_repetition(self):
        raw = ('<note>\n'+PAGE+'## 一、政策\n## 說明如下：\n'
               +'甲'*400+'\n\n'+TABLE+'\n'+'乙'*400+'\n')
        tagged = tag_comments(raw, None, TaggingMetadata(report_year='2025', stock_code='2330')).markdown
        for mode in ('original', 'parent_child'):
            doc = chunk_tagged(tagged, identity=('2025','2330'), source_sha256='b'*64,
                              config=replace(ChunkSettings(), mode=mode)).document
            occupied = set()
            for chunk in doc['chunks']:
                self.assertEqual(''.join(tagged[s['start']:s['end']] for s in chunk['source_spans']),
                                 content_body(chunk))
                for span in chunk['source_spans']:
                    positions = set(range(span['start'], span['end']))
                    self.assertFalse(occupied & positions)
                    occupied.update(positions)
            self.assertEqual(sum(c['content'].count(TABLE) for c in doc['chunks']), 1)


if __name__ == '__main__':
    unittest.main()
