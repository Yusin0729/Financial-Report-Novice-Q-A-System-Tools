"""EXPERIMENT_ONLY：只讀已保存候選進行重排，不載入索引或embedding模型。
停用EvaluationSettings.enabled並移除web action／history入口即可停用；舊報告保持不變。
"""
import copy
import hashlib
import json
import time
from dataclasses import replace
from statistics import mean
from Code_2.config.evaluation import EvaluationSettings
from Code_2.config.qa import QASettings
from Code_2.functions.experiments.export_output import reserve_qa_run, export_qa_run
from Code_2.functions.experiments.eval_run import export_batch
from Code_2.functions.experiments.eval_curve import build_curves
from Code_2.functions.experiments.eval_scoring import score


def load_source(settings, run, expected_hash=None):
    if not EvaluationSettings().enabled:
        raise ValueError('舊報告實驗功能已停用')
    from Code_2.functions.web.service import report_path
    path = report_path(settings, run, 'result.json')
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('來源報告超過128MB')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_hash is not None and expected_hash != digest:
        raise ValueError('來源報告已變更，請重新預覽；未呼叫API')
    source = json.loads(raw.decode('utf-8'))
    if not isinstance(source, dict):
        raise ValueError('來源報告格式無效')
    batch = source.get('schema_version') == 'financial-evaluation/1.0'
    if batch:
        from Code_2.functions.experiments.eval_scoring import SUPPORTED_RULES
        if source.get('scoring_rule') not in SUPPORTED_RULES[1:]:
            raise ValueError('來源評分版本不支援，避免混用未知規則')
        rows = source.get('rows')
    elif source.get('schema_version') == 'financial-qa/1.1':
        rows = [{'ID': 'single', 'Question': source.get('original_question'), 'query': source,
                 'status': source.get('status')}]
    else:
        raise ValueError('不支援這種報告；請選單題或Excel檢索報告')
    if not isinstance(rows, list) or not 1 <= len(rows) <= EvaluationSettings().max_rows:
        raise ValueError('來源題數無效')
    ids = [r.get('ID') for r in rows if isinstance(r, dict)]
    if len(ids) != len(rows) or any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('來源題號缺失或重複')
    return source, rows, batch, digest


def candidates(row, batch):
    if row.get('status') not in ('retrieved', 'reranked', 'answered', 'insufficient_evidence'):
        raise ValueError('這題未成功執行，不當成可重排結果')
    question = row.get('Question')
    if not isinstance(question, str) or not question.strip() or len(question) > QASettings().max_question_characters:
        raise ValueError('缺少有效原始問題')
    query = row.get('query')
    if not isinstance(query, dict):
        raise ValueError('缺少原始查詢結果')
    evidence = query.get('retrieved_evidence')
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= QASettings().max_retrieve_k:
        raise ValueError('缺少完整檢索候選；統計圖表報告不可重排')
    seen = set()
    for e in evidence:
        if (not isinstance(e, dict) or any(not isinstance(e.get(k), str) or not e[k] for k in ('id', 'chunk_id', 'doc_id', 'text'))
                or e['chunk_id'] in seen or not isinstance(e.get('page'), list) or not e['page']
                or any(type(v) is not int or v < 1 for v in e['page'])
                or type(e.get('retrieval_rank')) is not int or e['retrieval_rank'] < 1):
            raise ValueError('候選全文、來源或排名無效')
        seen.add(e['chunk_id'])
    metadata = {}
    if batch:
        ref = row.get('reference')
        details = row.get('scores', {}).get('returned', {}).get('top20')
        if not isinstance(ref, dict) or not isinstance(ref.get('expected_titles'), list) or not isinstance(ref.get('filter_years'), list):
            raise ValueError('缺少原始評分標準，不猜補標題或年度')
        if not isinstance(details, list):
            raise ValueError('缺少候選評分來源')
        metadata = {c['chunk_id']: c for c in details if isinstance(c, dict) and isinstance(c.get('chunk_id'), str)}
        for e in evidence:
            c = metadata.get(e['chunk_id'])
            if (c is None or c.get('doc_id') != e['doc_id'] or c.get('page') != e['page'] or c.get('text') != e['text']
                    or not isinstance(c.get('years'), list) or any(type(y) is not int for y in c['years'])
                    or not isinstance(c.get('note_title'), list) or not isinstance(c.get('sub_section'), str)):
                raise ValueError('候選全文與評分來源不一致，不回查向量庫猜補')
    return evidence, metadata


def requires_child_inputs(source,rows):
    for row in rows:
        query=row.get('query') or {}
        if query.get('candidate_unit')=='child':return True
        for e in query.get('retrieved_evidence',[]):
            if e.get('parent_relation') or (e.get('matched_chunk_ids') and e['matched_chunk_ids']!=[e.get('chunk_id')]):
                return True
    return False


def preview(settings, run, candidate_unit="returned"):
    source, rows, batch, digest = load_source(settings, run)
    if requires_child_inputs(source,rows):candidate_unit='child'
    child_context = None
    if candidate_unit == 'child':
        from Code_2.functions.experiments.child_candidates import ChildCandidates
        child_context = ChildCandidates(settings, source)
    elif candidate_unit != 'returned':
        raise ValueError('候選單位無效')
    result = []
    for row in rows:
        try:
            evidence, _ = child_context.inputs(row, batch) if child_context else candidates(row, batch)
            count, error = len(evidence), None
        except ValueError as e:
            count, error = 0, str(e)
        result.append({'ID': row['ID'], 'Question': row.get('Question', ''), 'candidate_count': count, 'error': error})
    return {'source_run': run, 'source_sha256': digest, 'batch': batch,
            'index_name': source.get('index', {}).get('display_name') or source.get('index_name') or source.get('collection'),
            'retrieve_k': source.get('settings', {}).get('retrieve_k') if batch else source.get('retrieve_k'),
            'candidate_unit': candidate_unit, 'rows': result, 'valid_count': sum(r['error'] is None for r in result)}


def validate_task(data, settings):
    allowed = {'action', 'source_run', 'source_sha256', 'ids', 'rerank_profile', 'evidence_k', 'generate_charts', 'candidate_unit'}
    if set(data) - allowed:
        raise ValueError('舊報告重排序欄位無效')
    source, rows, batch, digest = load_source(settings, data.get('source_run'), data.get('source_sha256'))
    ids = data.get('ids')
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('請勾選不重複的題目')
    available = {r['ID']: r for r in rows}
    if not set(ids).issubset(available):
        raise ValueError('所選題號不存在')
    unit = data.get('candidate_unit', 'returned')
    if requires_child_inputs(source,rows):unit='child'
    if unit not in ('child', 'returned'):
        raise ValueError('候選單位無效')
    child_context = None
    if unit == 'child':
        from Code_2.functions.experiments.child_candidates import ChildCandidates
        child_context = ChildCandidates(settings, source)
    for i in ids:
        (child_context.inputs(available[i], batch) if child_context else candidates(available[i], batch))
    k = data.get('evidence_k')
    retrieve = source.get('settings', {}).get('retrieve_k') if batch else source.get('retrieve_k')
    if type(retrieve) is not int or not 1 <= retrieve <= QASettings().max_retrieve_k:
        raise ValueError('來源召回數無效')
    if type(k) is not int or not 1 <= k <= retrieve:
        raise ValueError('保留證據數須介於1與來源召回數之間')
    charts = data.get('generate_charts', False)
    if type(charts) is not bool or (charts and not batch):
        raise ValueError('圖表僅適用Excel評分報告')
    from Code_2.functions.qa.rerankers import resolve_rerank_profile
    profile_id = data.get('rerank_profile')
    if not isinstance(profile_id, str) or not profile_id:
        raise ValueError('請選擇BGE或Voyage重排序設定')
    profile, _ = resolve_rerank_profile(settings.project_root, profile_id)
    if profile['provider'] not in ('voyage', 'bge'):
        raise ValueError('目前只支援BGE及Voyage重排序')
    return {'action': 'rerank-report', 'source_run': data['source_run'], 'source_sha256': digest,
            'ids': ids, 'rerank_profile': profile_id, 'evidence_k': k, 'generate_charts': charts, 'candidate_unit': unit}


def create_reranker(settings, qa):
    from Code_2.functions.qa.rerankers import create_reranker as factory
    return factory(settings, qa)


def run(data, settings, *, reranker_factory=create_reranker, progress=None):
    started = time.perf_counter()
    source, rows, batch, digest = load_source(settings, data['source_run'], data['source_sha256'])
    if requires_child_inputs(source,rows):data={**data,'candidate_unit':'child'}
    chosen = [r for r in rows if r['ID'] in data['ids']]
    if len(chosen) != len(data['ids']):
        raise ValueError('題號已變更，未呼叫API')
    child_context = None
    if data.get('candidate_unit') == 'child':
        from Code_2.functions.experiments.child_candidates import ChildCandidates
        child_context = ChildCandidates(settings, source)
    for row in chosen:
        (child_context.inputs(row, batch) if child_context else candidates(row, batch))
    current = replace(settings, export_enabled=True)
    paths = reserve_qa_run(current, mode='rerank')  # EXPERIMENT_ONLY：先確保可另存。
    qa = replace(QASettings(), evidence_k=data['evidence_k'], rerank_profile=data['rerank_profile'])
    reranker = None
    output = copy.deepcopy(source)
    lineage = {'source_run': data['source_run'], 'source_report_sha256': digest,
               'report_kind': 'saved_rerank', 'reused_candidates': True,
               'candidate_unit': data.get('candidate_unit', 'returned'),
               'candidate_input_order': 'chunk_id' if child_context else 'saved_evidence_order',
               'parent_expansion_stage': 'after_child_rerank' if child_context else 'before_rerank',
               'duplicate_parent_policy': 'merge_without_refill'}
    output.update(lineage)
    if batch:
        from Code_2.functions.experiments.eval_scoring import TITLE_RULE,NUMERIC_RULE
        output['source_scoring_rule']=source.get('scoring_rule')
        output['scoring_rule']=NUMERIC_RULE if any(r.get('reference',{}).get('numeric_targets') or r.get('reference',{}).get('Required_Numbers') for r in chosen) else TITLE_RULE
        output.update(rows=[], status='completed')
        output['settings'] = {**source['settings'], 'action': 'rerank-report', 'mode': 'rerank',
                              'rerank_enabled': True, 'rerank_profile': data['rerank_profile'],
                              'evidence_k': data['evidence_k'], 'generate_charts': data['generate_charts'],
                              'candidate_unit': data.get('candidate_unit', 'returned')}
    from Code_2.functions.experiments.evidence_report import EvidenceReportContext
    report_context = EvidenceReportContext(settings)
    stopped = False
    for number, row in enumerate(chosen, 1):
        if progress:
            progress(f"舊報告重排序 {number}/{len(chosen)}：ID {row['ID']}")
        entry = copy.deepcopy(row)
        for old_score in entry.get('scores',{}).values():
            old_score.setdefault('scoring_rule',source.get('scoring_rule'))
        q = copy.deepcopy(row['query'])
        q.update(lineage)
        for key in ('answer', 'generation', 'rerank', 'rerank_error', 'error', 'stage', 'export_status', 'output_dir', 'created_at'):
            q.pop(key, None)
        if 'query_embedding' in q:
            q['source_query_embedding'] = q.pop('query_embedding')
        q.update(mode='rerank', status='not_run', evidence=[], completed_stages=[],
                 reused_stages=['query_embedding', 'retrieval'], rerank_enabled=True, rerank_skipped=False,
                 evidence_k=data['evidence_k'], rerank_profile=data['rerank_profile'])
        entry.update(status='not_run', query=q, timings={}, elapsed_seconds=0, score=None,
                     raw_score=None, weighted_score=None, score_stage='rerank', usage={'rerank': {}})
        entry.pop('error', None)
        entry.get('scores', {}).pop('rerank', None)
        entry['content_tokens'] = {**entry.get('content_tokens', {}), 'rerank': None}
        before = time.perf_counter()
        if stopped:
            entry['error'] = '前題重排序失敗，未執行；原始候選仍保留'
        else:
            try:
                if reranker is None:
                    reranker, qa = reranker_factory(settings, qa)
                evidence, metadata = child_context.inputs(row, batch) if child_context else candidates(row, batch)
                selected, usage = reranker.rerank(row['Question'], copy.deepcopy(evidence))
                if child_context:
                    q['rerank_input_candidates'] = copy.deepcopy(evidence)
                    q['reranked_children'] = [report_context.enrich(e) for e in selected]
                    selected = child_context.expand(selected, row)
                # EXPERIMENT_ONLY：只在API完成後附加輸出標籤，不改送出的候選文字。
                selected = [report_context.enrich(e, metadata.get(e['chunk_id'])) for e in selected]
                q.update(status='reranked', evidence=selected, rerank=usage, rerank_model=qa.rerank_model, rerank_provider=qa.rerank_provider,
                         completed_stages=['rerank'])
                entry.update(status='reranked', usage={'rerank': usage})
                if batch:
                    cs = []
                    for e in selected:
                        source_node = metadata.get(e['chunk_id']) or report_context.node(e)
                        if not isinstance(source_node,dict):raise ValueError('找不到相符來源父項作評分')
                        c = copy.deepcopy(source_node)
                        c['parent_id'] = c.get('group_id') if c.get('group_id') != c['chunk_id'] else None
                        cs.append({'chunk': c, 'rank': e['rerank_rank'], 'text': e['text'],
                                   'matched_chunk_ids': e['matched_chunk_ids'], 'parent_relation': e.get('parent_relation')})
                    s = score(row['reference'], cs, retrieve_k=source['settings']['retrieve_k'])
                    entry['scores']['rerank'] = s
                    entry.update(score=s['score'], weighted_score=s['weighted_score'], raw_score=s['raw_score'])
            except (Exception, KeyboardInterrupt) as e:
                import re
                from Code_2.functions.qa.bge_reranker import BgeRerankError
                safe = str(e) if isinstance(e, BgeRerankError) else str(e) if re.fullmatch(r'Voyage重排序失敗（[A-Za-z_][A-Za-z0-9_]*）；未截斷、未重試', str(e)) else f'重排序失敗（{type(e).__name__}）；未自動重試'
                entry.update(status='failed', error=safe)
                q.update(status='failed', stage='rerank', error=entry['error'])
                stopped = True
        entry['elapsed_seconds'] = round(time.perf_counter() - before, 6)
        entry['timings'] = {'rerank': entry['elapsed_seconds']} if entry['status'] != 'not_run' else {}
        if batch:
            output['rows'].append(entry)
        else:
            output = q
    elapsed = round(time.perf_counter() - started, 6)
    output.update(elapsed_seconds=elapsed, export_status='saved', output_dir=str(paths['json'].parent), created_at=paths['created_at'])
    try:
        if batch:
            done = [r for r in output['rows'] if r['status'] == 'reranked' and r['score'] is not None]
            output['status'] = 'needs_attention' if stopped else 'completed'
            output['summary'] = {'selected': len(chosen), 'scored': len(done),
                'mean_score': round(mean(r['score'] for r in done), 4) if done else None,
                'mean_weighted_score': round(mean(r['weighted_score'] for r in done), 4) if done else None,
                'mean_raw_score': round(mean(r['raw_score'] for r in done), 4) if done else None,
                'failed': sum(r['status'] == 'failed' for r in output['rows']),
                'not_run': sum(r['status'] == 'not_run' for r in output['rows']), 'unavailable': 0}
            output['settings'].update(rerank_model=qa.rerank_model, rerank_provider=qa.rerank_provider)
            output['charts_requested'] = data['generate_charts']
            output['curves'] = build_curves(output['rows'], source['settings']['retrieve_k']) if data['generate_charts'] else {}
            output['raw_curves'] = build_curves(output['rows'], source['settings']['retrieve_k'], metric='raw') if data['generate_charts'] else {}
            export_batch(paths, output)
        else:
            export_qa_run(current, paths, output)
    except (OSError, ValueError, TypeError) as e:
        output.update(export_status='failed', export_error=f'另存失敗（{type(e).__name__}），請保留畫面結果')
    return {'action': 'evaluate' if batch else 'query', 'evaluation' if batch else 'query': output}
