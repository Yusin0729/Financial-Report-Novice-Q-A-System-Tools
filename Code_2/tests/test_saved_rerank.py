"""舊報告固定候選重排測試；全部使用假服務，不呼叫付費API。"""
import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from Code_2.config.embedding import Settings
from Code_2.functions.experiments.eval_scoring import score
from Code_2.functions.experiments import saved_rerank as replay
from Code_2.functions.web.service import validate_task, execute_task


class SavedRerankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = replace(Settings(), project_root=Path(self.temp.name))
        self.name = 'qa_20261027_00-00-00_000001'
        self.folder = self.settings.response_dir / self.name
        self.folder.mkdir(parents=True)
        self.ref = {'stock_code': '2330', 'filter_years': [2024], 'expected_pages': [], 'expected_titles': ['營業收入']}
        self.ev = []
        cs = []
        for i, title in enumerate(['其他資料', '營業收入'], 1):
            c = {'chunk_id': f'doc__c{i:05d}', 'doc_id': '2024Q4_2330_Financial_Report',
                 'years': [2024], 'page': [55], 'sub_section': title, 'note_title': [], 'parent_id': None}
            text = title + '完整本文'
            cs.append({'chunk': c, 'rank': i, 'text': text})
            self.ev.append({'id': 'S'+str(i), 'chunk_id': c['chunk_id'], 'doc_id': c['doc_id'],
                'page': [55], 'text': text, 'retrieval_rank': i, 'retrieval_distance': .2,
                'matched_chunk_ids': [c['chunk_id']], 'parent_relation': None})
        s = score(self.ref, cs, retrieve_k=50)
        query = {'schema_version': 'financial-qa/1.1', 'original_question': '營業收入是多少？',
            'status': 'retrieved', 'mode': 'retrieve', 'backend': 'bge', 'collection': 'financial_'+'a'*24,
            'retrieve_k': 50, 'retrieved_evidence': self.ev, 'evidence': [],
            'completed_stages': ['query_embedding', 'retrieval'], 'query_embedding': {'historical': True}}
        self.source = {'schema_version': 'financial-evaluation/1.0', 'scoring_rule': 'year-title-dual/3.1',
            'filename': '測試.xlsx', 'sheet': '題目', 'settings': {'retrieve_k': 50},
            'rows': [{'ID': '1', 'Question': query['original_question'], 'status': 'retrieved', 'query': query,
                'reference': self.ref, 'scores': {'retrieval': s, 'returned': s}, 'raw_score': 10,
                'weighted_score': 9.8, 'score': 9.8, 'score_stage': 'returned'}]}
        self.write()
        self.profile = patch('Code.functions.embedding.api_settings.resolve_profile', return_value=({'provider': 'voyage', 'model': 'rerank-3-lite'}, 'fake-secret'))
        self.profile.start()

    def tearDown(self):
        self.profile.stop()
        self.temp.cleanup()

    def write(self):
        (self.folder/'result.json').write_text(json.dumps(self.source, ensure_ascii=False), encoding='utf-8')
        (self.folder/'answer.md').write_text('舊報告不可覆寫', encoding='utf-8')

    def task(self, **changes):
        return validate_task({'action': 'rerank-report', 'source_run': self.name, 'ids': ['1'],
            'rerank_profile': 'profile', 'evidence_k': 1, 'generate_charts': True, **changes}, self.settings)

    def factory(self, calls, fail=False):
        class Fake:
            def rerank(inner, question, evidence):
                calls.append((question, copy.deepcopy(evidence)))
                if fail:
                    raise RuntimeError('secret HTTP body should not leak')
                return [{**evidence[-1], 'rerank_rank': 1, 'rerank_score': .9}], {'model': 'rerank-3-lite', 'total_tokens': 25}
        return lambda settings, qa: (Fake(), qa)

    def test_reuse_exact_candidates_without_embedding_and_preserve_source(self):
        raw = (self.folder/'result.json').read_bytes()
        t = self.task()
        t = validate_task(t, self.settings)  # worker二次驗證。
        calls = []
        with patch('Code_2.functions.qa.pipeline.ask', side_effect=AssertionError('不可重新檢索')), patch('Code.functions.embedding.providers.create_provider', side_effect=AssertionError('不可embedding')):
            r = replay.run(t, self.settings, reranker_factory=self.factory(calls))['evaluation']
        self.assertEqual(calls[0][1], self.ev)
        self.assertEqual(r['rows'][0]['query']['completed_stages'], ['rerank'])
        self.assertEqual(r['rows'][0]['scores']['rerank']['score'], 10)
        self.assertEqual(r['rows'][0]['scores']['returned']['score'], 9.8)
        self.assertEqual(r['summary']['scored'], 1)
        self.assertEqual(r['source_report_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual((self.folder/'result.json').read_bytes(), raw)
        self.assertEqual((self.folder/'answer.md').read_text(encoding='utf-8'), '舊報告不可覆寫')
        dest = Path(r['output_dir'])
        self.assertNotEqual(dest, self.folder)
        for name in ('result.json', 'answer.md', 'results.xlsx', '測試分析報告.md', 'ID_001.md', 'ID_001.json'):
            self.assertTrue((dest/name).is_file())
        self.assertIn('重排序', (dest/'測試分析報告.md').read_text(encoding='utf-8'))
        self.assertIn('只依以下證據回答', (dest/'ID_001.md').read_text(encoding='utf-8'))
        self.assertNotIn('Required_Numbers', (dest/'ID_001.json').read_text(encoding='utf-8'))
        self.assertTrue(r['raw_curves']['rerank']['points'])
        self.assertNotIn('fake-secret', (dest/'result.json').read_text(encoding='utf-8'))

    def test_failure_preserves_partial_and_stops_later_rows(self):
        second = copy.deepcopy(self.source['rows'][0]);second['ID']='2'
        self.source['rows'].append(second);self.write()
        t=self.task(ids=['1','2']);calls=[]
        r=replay.run(t,self.settings,reranker_factory=self.factory(calls,True))['evaluation']
        self.assertEqual(len(calls),1)
        self.assertEqual([x['status'] for x in r['rows']],['failed','not_run'])
        self.assertEqual(r['summary']['failed'],1)
        self.assertEqual(r['summary']['not_run'],1)
        self.assertEqual(r['export_status'],'saved')
        self.assertNotIn('secret HTTP',json.dumps(r))

    def test_source_changed_after_preview_rejected_before_api(self):
        t=self.task();self.source['sheet']='changed';self.write()
        calls=[]
        with self.assertRaisesRegex(ValueError,'已變更'):
            replay.run(t,self.settings,reranker_factory=self.factory(calls))
        self.assertFalse(calls)

    def test_preview_excludes_failed_or_missing_candidates(self):
        self.source['rows'].append({'ID':'2','Question':'失敗問題','status':'failed'})
        self.write();r=replay.preview(self.settings,self.name)
        self.assertEqual(r['valid_count'],1)
        self.assertTrue(r['rows'][1]['error'])
        with self.assertRaises(ValueError):self.task(ids=['2'])

    def test_invalid_path_parameters_and_missing_metadata(self):
        for changes in ({'source_run':'../.env'},{'evidence_k':True},{'evidence_k':51},{'ids':['1','1']},{'generate_charts':'yes'},{'unexpected':True}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.task(**changes)
        self.source['rows'][0]['scores']['returned']['top20'][0]['text']='not same'
        self.write()
        with self.assertRaisesRegex(ValueError,'不一致'):self.task()

    def test_single_report_and_dispatch(self):
        self.source=self.source['rows'][0]['query'];self.write()
        t=self.task(ids=['single'],generate_charts=False);calls=[]
        result=replay.run(t,self.settings,reranker_factory=self.factory(calls))
        self.assertEqual(result['action'],'query')
        self.assertEqual(result['query']['status'],'reranked')
        self.assertTrue(Path(result['query']['output_dir'],'answer.md').is_file())
        with patch('Code_2.functions.experiments.saved_rerank.run',return_value=result) as run:
            self.assertEqual(execute_task(t,self.settings),result)
            run.assert_called_once()

    def test_child_topk_before_parent_and_output_tags_only(self):
        from Code.functions.content_context import context_prefix
        from Code_2.functions.experiments.child_candidates import ChildCandidates
        doc='2024Q4_2330_Financial_Report'
        def node(cid,text,parent=None):
            c={'chunk_id':cid,'doc_id':doc,'years':[2024],'page':[55],
                'main_section':'合併財務報告附註','sub_section':'營業收入','note_title':['客戶合約'],
                'content_type':'text','table_context':'','directions':[],
                'parent_id':parent,'parent_relation':'content' if parent else None,
                'node_type':'chunk','source_spans':[]}
            c['content_prefix']=context_prefix(c);c['content']=c['content_prefix']+text
            return c
        c1=node('child1','第一個子項','parent1');c2=node('child2','第二個子項','parent1');c3=node('child3','第三個子項')
        parent=node('parent1','完整父層正文不能截斷');parent['node_type']='content_parent'
        chunk_file=self.settings.input_dir/'batch'/'parent_child'/'2024_2330_chunk_250.json'
        chunk_file.parent.mkdir(parents=True)
        raw=json.dumps({'doc_id':doc,'chunks':[c3,c2,c1],'parents':[parent]},ensure_ascii=False).encode()
        chunk_file.write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
        originals=[];cs=[]
        for i,c in enumerate([parent,c3],1):
            ids=['child1','child2'] if i==1 else ['child3']
            e={'id':f'S{i}','chunk_id':c['chunk_id'],'doc_id':doc,'page':[55],'text':c['content'],
                'input_sha256':digest,'matched_chunk_ids':ids,'retrieval_rank':i,
                'parent_relation':'content' if i==1 else None}
            originals.append(e);cs.append({'chunk':c,'rank':i,'text':e['text']})
        r=self.source['rows'][0];r['query']['retrieved_evidence']=originals
        r['scores']={'returned':score(self.ref,cs,retrieve_k=50)}
        r['raw_top20_chunk_ids']=['child1'];self.write()
        inputs,_=ChildCandidates(self.settings,self.source).inputs(r,True)
        self.assertEqual([e['chunk_id'] for e in inputs],['child1','child2','child3'])
        self.assertEqual(inputs[0]['source_retrieval_rank'],1)
        self.assertIsNone(inputs[1]['source_retrieval_rank'])
        calls=[]
        class Fake:
            def rerank(inner,question,evidence):
                calls.append(copy.deepcopy(evidence))
                return [{**evidence[0],'rerank_rank':1,'rerank_score':.9},
                        {**evidence[1],'rerank_rank':2,'rerank_score':.8}],{'total_tokens':10}
        t=self.task(candidate_unit='child',evidence_k=2)
        result=replay.run(t,self.settings,reranker_factory=lambda s,q:(Fake(),q))['evaluation']
        q=result['rows'][0]['query']
        self.assertEqual(len(q['reranked_children']),2)
        self.assertEqual(len(q['evidence']),1)  # 同父項合併，不補第3個子項。
        self.assertEqual(q['evidence'][0]['matched_chunk_ids'],['child1','child2'])
        self.assertEqual(q['evidence'][0]['report_metadata']['stock_code'],'2330')
        self.assertIn('完整父層正文不能截斷',q['evidence'][0]['text'])
        self.assertEqual(calls[0][0]['text'],c1['content'])
        self.assertNotIn('股票代號',calls[0][0]['text'])
        md=Path(result['output_dir'],'answer.md').read_text(encoding='utf-8')
        self.assertIn('子項Top 2',md);self.assertIn('完整父層正文不能截斷',md)
        self.assertIn('股票代號：2330',md)
        self.assertEqual(q['parent_expansion_stage'],'after_child_rerank')

    def test_child_mode_rejects_missing_source_before_api(self):
        with self.assertRaisesRegex(ValueError,'SHA256相符'):
            self.task(candidate_unit='child')

    def test_http_preview_and_submit(self):
        import threading
        import urllib.request
        from Code_2.config.web import WebSettings
        from Code_2.functions.web.server import create_server
        class FakeJobs:
            thread=None
            def snapshot(inner):return None
            def start(inner, task):
                inner.task=task
                return {'id':'test-job','status':'running','action':task['action']}
        jobs=FakeJobs()
        server,_=create_server(self.settings,replace(WebSettings(),port=0),jobs=jobs)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            html=urllib.request.urlopen(base+'/').read().decode()
            self.assertIn('saved-rerank-panel',html)
            token=html.split('name="app-token" content="')[1].split('"')[0]
            preview=json.load(urllib.request.urlopen(base+'/api/rerank-source?run='+self.name))
            self.assertEqual(preview['valid_count'],1)
            self.assertEqual(preview['retrieve_k'],50)
            script=urllib.request.urlopen(base+'/saved-rerank.js').read().decode()
            self.assertIn("action:'rerank-report'",script)
            request=urllib.request.Request(base+'/api/tasks',data=json.dumps(self.task()).encode(),
                headers={'Content-Type':'application/json','X-App-Token':token},method='POST')
            result=json.load(urllib.request.urlopen(request))
            self.assertEqual(result['job']['action'],'rerank-report')
            self.assertEqual(jobs.task['source_sha256'],preview['source_sha256'])
        finally:
            server.shutdown();thread.join();server.server_close()


if __name__ == '__main__':unittest.main()
