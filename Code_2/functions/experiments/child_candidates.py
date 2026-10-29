"""EXPERIMENT_ONLY：由舊報告命中ID還原子項；先重排TopK子項，再召回必回父項。"""
import copy
from Code.functions.embedding.prepare import embedding_context
from Code.functions.embedding.table_text import convert_content
from Code_2.functions.experiments.evidence_report import EvidenceReportContext


class ChildCandidates:
    def __init__(self, settings, source):
        self.context = EvidenceReportContext(settings)
        self.text_cache = {}
        signature = source.get('index', {}).get('signature') or source.get('query_embedding', {}).get('model', {})
        fields = signature.get('fields')
        if fields is not None and [(p, r) for p, r in fields if r in ('embedding', 'both')] != [('embedding_text', 'embedding')]:
            raise ValueError('這份索引不是只以embedding_text向量化，不能猜補舊子項輸入')

    def inputs(self, row, batch):
        from Code_2.functions.experiments.saved_rerank import candidates
        parents, metadata = candidates(row, batch)
        known = {cid: i for i, cid in enumerate(row.get('raw_top20_chunk_ids', []), 1)}
        children = {}
        for parent in parents:
            ids = parent.get('matched_chunk_ids')
            if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
                raise ValueError('舊報告缺少命中子項ID，不能用父項假代替')
            for cid in ids:
                if cid in children:
                    continue
                locator = {**parent, 'chunk_id': cid}
                node = self.context.node(locator)
                if node is None or node.get('node_type') not in ('chunk', None):
                    raise ValueError('找不到SHA256相符的原始子項，未重新檢索或外傳')
                group = node.get('parent_id') or cid
                if group != parent['chunk_id'] and cid != parent['chunk_id']:
                    # 可選標題父項不是必回群組，不用它替代真正父項。
                    if parent.get('parent_relation') == 'heading':
                        continue
                    raise ValueError('子項與來源父項關係不符')
                key = (node['doc_id'], parent['input_sha256'], cid)
                if key not in self.text_cache:
                    body, _ = convert_content(node['content'])
                    context = embedding_context(node)
                    self.text_cache[key] = context + '\n\n' + body if context else body
                text = self.text_cache[key]
                children[cid] = {'id': '', 'chunk_id': cid, 'doc_id': node['doc_id'], 'page': node['page'],
                    'text': text, 'input_sha256': parent['input_sha256'], 'matched_chunk_ids': [cid],
                    'parent_id': node.get('parent_id'), 'parent_relation': node.get('parent_relation'),
                    'source_spans': node.get('source_spans'), 'retrieval_rank': parent.get('retrieval_rank') if cid==parent['chunk_id'] else known.get(cid),
                    'retrieval_distance': parent.get('retrieval_distance',0.0),
                    'source_retrieval_rank': known.get(cid), 'return_evidence_id': group}
        output = []
        for order, cid in enumerate(sorted(children), 1):
            child = children[cid]
            child.update(id=f'C{order}', candidate_input_order=order)
            output.append(child)
        expected = row.get('query', {}).get('retrieve_k')
        if not output or (isinstance(expected, int) and len(output) > expected):
            raise ValueError('還原子項數量與來源召回數不符')
        return output, metadata

    def expand(self, selected, row):
        # Reconstruct only selected nodes, then use the same expansion path as live QA.
        from Code_2.functions.qa.pipeline import evidence_rows
        rows=[]
        for number,child in enumerate(selected,1):
            node=self.context.node(child)
            if node is None:raise ValueError('找不到重排後子項的原始來源')
            parent=self.context.node({**child,'chunk_id':node['parent_id']}) if node.get('parent_id') else None
            heading=self.context.node({**child,'chunk_id':node['heading_parent_id']}) if node.get('heading_parent_id') else None
            rows.append({'chunk_id':child['chunk_id'],'distance':child.get('retrieval_distance',0.0),
                '_retrieval_rank':child.get('retrieval_rank') or child.get('candidate_input_order') or number,
                'metadata':{'_sys_chunk_id':child['chunk_id'],'_sys_doc_id':child['doc_id'],'_sys_input_sha256':child['input_sha256']},
                'payload':{'schema_version':'financial-vector-payload/1.0','input_sha256':child['input_sha256'],
                           'original_chunk':node,'original_parent':parent,'original_heading_parent':heading},
                **{k:child[k] for k in ('rerank_rank','rerank_score','rerank_raw_score') if k in child}})
        return evidence_rows(rows,include_heading_parent=bool(row['query'].get('include_heading_parent')))

