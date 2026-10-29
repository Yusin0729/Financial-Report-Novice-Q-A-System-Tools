import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
from Code_2.config.embedding import Settings
from Code_2.config.qa import QASettings
from Code_2.functions.qa.pipeline import ask,evidence_rows
from Code_2.tests.test_qa import raw_row,INDEX,PROFILE

def rows():
    result=[]
    for i,body in enumerate(('甲','乙','丙'),1):
        row=deepcopy(raw_row());cid=f'child{i}'
        child=row['payload']['original_chunk'];child.update(chunk_id=cid,content=body,page=[i],parent_id='p12' if i<3 else 'p3',parent_relation='content',heading_parent_id='heading')
        parent=deepcopy(child);parent.update(chunk_id=child['parent_id'],content='甲乙' if i<3 else '丙',page=[1,2] if i<3 else [3],parent_id=None)
        heading=deepcopy(child);heading.update(chunk_id='heading',content='甲乙丙 父層專用內容',page=[1,2,3],node_type='heading_parent',parent_id=None)
        row.update(chunk_id=cid,distance=i/10)
        row['metadata']['_sys_chunk_id']=cid
        row['payload'].update(original_parent=parent,original_heading_parent=heading)
        result.append(row)
    return result

class ParentExpansionOrderTests(unittest.TestCase):
    def execute(self,*,heading=False,rerank=True,mode='rerank',original=False):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        settings=Settings(project_root=Path(temporary.name));raw=rows()
        index=deepcopy(INDEX);index['signature'].update(source_chunk_rule='content-end-original/1.4' if original else 'bounded-parent-child/5.6',chunking={'mode':'original' if original else 'parent_child'})
        provider=Mock(profile=PROFILE);provider.embed.return_value=[[1.,0.]]
        store=Mock(collection_name='test');store.search.return_value=raw
        reranker=Mock();answerer=Mock();seen=[]
        def rank(question,candidates):
            seen.extend(candidates)
            self.assertEqual([c['chunk_id'] for c in candidates],['child1','child2','child3'])
            self.assertTrue(all('父層專用內容' not in c['text'] for c in candidates))
            return [{**candidates[1],'rerank_rank':1,'rerank_score':.9},{**candidates[0],'rerank_rank':2,'rerank_score':.8}],{'total_tokens':10}
        reranker.rerank.side_effect=rank
        answerer.answer.return_value=({'status':'answered','format':'markdown','text':'答案由模型計算'}, {})
        qa=replace(QASettings(),retrieve_k=3,evidence_k=2,include_heading_parent=heading,rerank_enabled=rerank)
        result=ask('問題',settings,index=index,qa=qa,mode=mode,provider_factory=lambda *a:provider,
            store_factory=lambda *a,**kw:store,service_factory=lambda *a:(reranker,answerer))
        self.assertNotEqual(result['status'],'failed',result)
        return result,seen,reranker,answerer

    def test_only_selected_children_expand_and_same_parent_is_not_refilled(self):
        result,_,_,_=self.execute()
        self.assertEqual(result['selected_child_ids'],['child2','child1'])
        self.assertEqual([e['chunk_id'] for e in result['evidence']],['p12'])
        parent=result['evidence'][0]
        self.assertEqual(parent['matched_chunk_ids'],['child2','child1'])
        self.assertEqual(parent['selected_child_ranks'],[1,2])
        self.assertEqual(parent['retrieval_rank'],2)
        self.assertEqual(parent['rerank_rank'],1)
        self.assertEqual(parent['rerank_score'],.9)

    def test_heading_parent_is_added_after_rerank_and_llm_receives_parents(self):
        result,seen,_,answerer=self.execute(heading=True,mode='answer')
        self.assertEqual(len(seen),3)
        self.assertEqual([e['chunk_id'] for e in result['evidence']],['p12','heading'])
        self.assertEqual(answerer.answer.call_args.args[1],result['evidence'])
        self.assertEqual(len(result['retrieved_evidence']),3)
        self.assertEqual(len(result['reranked_evidence']),2)

    def test_no_rerank_selects_top_k_before_expanding(self):
        result,_,reranker,_=self.execute(rerank=False,mode='answer')
        reranker.rerank.assert_not_called()
        self.assertEqual(result['selected_child_ids'],['child1','child2'])
        self.assertEqual([e['chunk_id'] for e in result['evidence']],['p12'])

    def test_retrieve_only_and_original_never_add_heading_parent(self):
        result,_,reranker,_=self.execute(heading=True,mode='retrieve',original=True)
        reranker.rerank.assert_not_called()
        self.assertEqual([e['chunk_id'] for e in result['evidence']],['p12'])

    def test_table_parent_is_not_in_candidate_input(self):
        raw=rows()
        for row in raw:row['payload']['original_chunk']['parent_relation']='table'
        children=evidence_rows(raw,expand_parents=False)
        self.assertEqual([c['chunk_id'] for c in children],['child1','child2','child3'])
        self.assertEqual(len(evidence_rows(raw[:2])),1)

if __name__=='__main__':unittest.main()
