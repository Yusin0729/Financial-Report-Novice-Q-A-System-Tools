"""原題→同模型已提交索引→可選BGE／Voyage重排→Gemini／GPT；失敗明確停止、不寫問題日誌。"""
from dataclasses import replace
import re
import math
import time
from Code_2.config.embedding import INDEX_RULE, PREPARE_RULE
from Code_2.config.qa import QASettings, PROMPT_VERSION, MODE_LABELS, gemini_prompt
from Code_2.functions.embedding.providers import create_provider, validate_vectors
from Code_2.functions.embedding.keys import service_key
from Code_2.functions.embedding.store import ChromaStore
from Code_2.functions.embedding.table_text import convert_content
from Code_2.functions.embedding.prepare import title_context, embedding_context
from Code_2.functions.qa.catalog import list_indexes, select_index
from Code_2.functions.qa.services import VoyageReranker, GeminiAnswerer
from Code_2.functions.qa.answers import validate_answer
from Code.functions.content_context import content_body
from Code.functions.parent_relations import contains


def build_filters(signature, stock_code=None, report_year=None):
    allowed = {path.split('.')[-1] for path, role in signature.get('fields', []) if role in ('metadata', 'both')}
    parts = []
    if stock_code is not None:
        if not isinstance(stock_code, str) or not re.fullmatch(r'\d+', stock_code):
            raise ValueError('股票代號須為數字字串，保留前導0')
        parts.append(('stock_code', stock_code))
    if report_year is not None:
        values = report_year if isinstance(report_year, list) else [report_year]
        if not values or any(type(y) is not int or not 1900 <= y <= 2199 for y in values):
            raise ValueError('年度須為西元整數或非空年度清單')
        parts.append(('years', list(dict.fromkeys(values))))
    if any(key not in allowed for key, _ in parts):
        raise ValueError('所選索引未儲存所需篩選欄位；不忽略篩選或擅自重建')
    clauses = []
    for key, value in parts:
        if key != 'years':
            clauses.append({key: value})
        else:
            terms = [{'years': {'$contains': year}} for year in value]
            clauses.append({'$or': terms} if len(terms) > 1 else terms[0])
    return {'$and': clauses} if len(clauses) > 1 else clauses[0] if clauses else None


def evidence_rows(rows, *, include_heading_parent=False):
    output, seen, parents = [], set(), {}
    def append_evidence(value,matched_id,rank,row,relation):
        cid=value['chunk_id']
        if cid in parents:
            if value != parents[cid][0]:
                raise ValueError('同一父項的召回內容不一致')
            if matched_id not in parents[cid][1]['matched_chunk_ids']:
                parents[cid][1]['matched_chunk_ids'].append(matched_id)
            return
        body,_=convert_content(value['content'])
        context=embedding_context(value)
        evidence={'id':f'S{len(output)+1}','chunk_id':cid,'doc_id':value['doc_id'],'page':value['page'],
                  'text':context+'\n\n'+body if context else body,'source_spans':value.get('source_spans'),
                  'matched_chunk_ids':[matched_id], 'parent_id':cid if relation else None,
                  'parent_relation':relation,'input_sha256':row['payload']['input_sha256'],
                  'retrieval_rank':rank,'retrieval_distance':row['distance']}
        output.append(evidence)
        parents[cid]=(value,evidence)
    for rank, row in enumerate(rows, 1):
        payload, meta = row['payload'], row['metadata']
        chunk = payload.get('original_chunk', {})
        cid, doc_id, pages = chunk.get('chunk_id'), chunk.get('doc_id'), chunk.get('page')
        if (payload.get('schema_version') != 'financial-vector-payload/1.0' or cid != row['chunk_id'] or
                cid in seen or cid != meta.get('_sys_chunk_id') or doc_id != meta.get('_sys_doc_id') or
                not isinstance(doc_id, str) or not isinstance(pages, list) or not pages or
                any(type(p) is not int or p < 1 for p in pages) or
                type(row['distance']) not in (int, float) or not math.isfinite(row['distance']) or
                payload.get('input_sha256') != meta.get('_sys_input_sha256')):
            raise ValueError('召回來源識別、頁碼或payload錯配')
        seen.add(cid)
        matched_id = cid
        parent_id = chunk.get('parent_id')
        heading_id=chunk.get('heading_parent_id')
        heading=payload.get('original_heading_parent')
        if include_heading_parent and heading_id is not None:
            if (not isinstance(heading,dict) or heading.get('chunk_id')!=heading_id
                    or heading.get('node_type')!='heading_parent' or not contains(heading,chunk)):
                raise ValueError('標題父項缺失或與命中子項錯配')
        if parent_id is not None:
            parent = payload.get('original_parent')
            if (not isinstance(parent, dict) or parent.get('chunk_id') != parent_id or
                    parent.get('doc_id') != doc_id or not contains(parent,chunk) or
                    not set(pages).issubset(parent.get('page', []))):
                raise ValueError('完整父表與召回子塊錯配')
            relation=chunk.get('parent_relation') or 'legacy'
            append_evidence(parent,matched_id,rank,row,relation)
        else:
            append_evidence(chunk,matched_id,rank,row,None)
        if include_heading_parent and heading_id is not None:
            append_evidence(heading,matched_id,rank,row,'heading')
    return output


def ask(question, settings, *, backend='bge', collection=None, stock_code=None, report_year=None,
        mode='answer', qa=None, index=None, provider_factory=create_provider, store_factory=ChromaStore,
        service_factory=None, observer=None):
    qa = qa or QASettings()
    stage = 'validate_input'
    def observe(name, **values):
        if observer is not None:
            observer(name, values)
    base = {'schema_version': 'financial-qa/1.1', 'original_question': question, 'mode': mode,
            'completed_stages': [],
            'rewrite_enabled': False, 'prompt_version': PROMPT_VERSION,
            'retrieved_evidence': [], 'evidence': [], 'status': 'failed'}
    store, client = None, None
    try:
        if mode not in MODE_LABELS:
            raise ValueError('模式須為retrieve／rerank／answer')
        if not isinstance(question, str) or not question.strip():
            raise ValueError('問題不得空白')
        if (type(qa.retrieve_k) is not int or type(qa.evidence_k) is not int or
                not 1 <= qa.retrieve_k <= qa.max_retrieve_k or
                not 1 <= qa.evidence_k <= qa.max_retrieve_k or
                (mode != 'retrieve' and qa.evidence_k > qa.retrieve_k)):
            raise ValueError('檢索數量無效')
        if len(question) > qa.max_question_characters:
            raise ValueError('問題過長，未截斷或發送')
        if type(qa.rerank_enabled) is not bool or (mode == 'rerank' and not qa.rerank_enabled):
            raise ValueError('重排序模式與開關不一致')
        if type(qa.include_heading_parent) is not bool:
            raise ValueError('標題父項召回開關須為布林值')
        need_rerank = mode == 'rerank' or (mode == 'answer' and qa.rerank_enabled)
        stage = 'select_index'
        index = index or select_index(list_indexes(settings, backend), backend, collection)
        signature = index['signature']
        is_original = (str(signature.get('source_chunk_rule', '')).startswith('content-end-original/')
                       or signature.get('chunking', {}).get('mode') == 'original')
        if is_original and qa.include_heading_parent:
            qa = replace(qa, include_heading_parent=False)
        if qa.include_heading_parent and not re.match(r'^(bounded-parent-child/|content-end-original/1\.0$)',str(signature.get('source_chunk_rule') or '')):
            raise ValueError('所選索引沒有新版標題父項關係，請使用Code第五階段建立新版切分索引')
        if (index['backend'] != backend or signature.get('rule') != INDEX_RULE or
                signature.get('preparation_rule') != PREPARE_RULE):
            raise ValueError('索引規則不符：舊索引不支援新的years及父子資料；請重新前處理並建庫至新collection')
        where = build_filters(signature, stock_code, report_year)
        rerank_key = answer_key = None
        if need_rerank and qa.rerank_profile:
            from Code.functions.embedding.api_settings import resolve_profile
            from Code_2.functions.qa.rerankers import resolve_rerank_profile
            profile, rerank_key = resolve_rerank_profile(settings.project_root, qa.rerank_profile)
            qa = replace(qa, rerank_model=profile['model'], rerank_provider=profile['provider'])
        if mode == 'answer' and qa.answer_profile:
            from Code.functions.embedding.api_settings import resolve_profile
            profile, answer_key = resolve_profile(settings.project_root, qa.answer_profile, 'answer')
            qa = replace(qa, answer_model=profile['model'], answer_provider=profile['provider'])
        if mode == 'answer' and qa.answer_provider not in ('gemini', 'openai'):
            raise ValueError('回答服務商不支援')
        base.update(backend=backend, collection=index['collection'], index_name=index.get('display_name', index['collection']), filters=where,
                    retrieve_k=qa.retrieve_k, evidence_k=qa.evidence_k,
                    rerank_model=qa.rerank_model, rerank_provider=qa.rerank_provider, answer_model=qa.answer_model, answer_provider=qa.answer_provider,
                    rerank_profile=qa.rerank_profile if need_rerank else None, answer_profile=qa.answer_profile,
                    rerank_enabled=need_rerank, rerank_skipped=mode=='answer' and not need_rerank,
                    embedding_profile=settings.embedding_profile)
        base['include_heading_parent']=qa.include_heading_parent
        stage = 'service_setup'
        # 僅建立所選模式需要的服務；BGE只排序不讀任何API金鑰。
        if mode != 'retrieve' and service_factory is None:
            if need_rerank and qa.rerank_provider == 'bge':
                from Code_2.functions.qa.bge_reranker import BgeReranker
                reranker = BgeReranker(settings, qa)
            elif need_rerank:
                voyage = rerank_key or service_key(settings.project_root, 'VOYAGE_API_KEY')
                import voyageai
                client = voyageai.Client(api_key=voyage, timeout=qa.timeout, max_retries=0)
                reranker = VoyageReranker(client, qa)
            if mode == 'answer':
                answer_key = answer_key or service_key(settings.project_root,
                    'OPENAI_API_KEY' if qa.answer_provider == 'openai' else 'GEMINI_API_KEY')
                if qa.answer_provider == 'openai':
                    from Code_2.functions.qa.openai_answer import OpenAIAnswerer
                    answerer = OpenAIAnswerer(answer_key, qa)
                else:
                    answerer = GeminiAnswerer(answer_key, qa)
        elif mode != 'retrieve':
            reranker, answerer = service_factory(qa)
        stage = 'query_embedding'
        phase_started = time.perf_counter()
        provider_settings = replace(settings, allow_voyage_api=True) if backend == 'voyage' else settings
        provider = provider_factory(backend, provider_settings)
        if provider.profile != signature['model']:
            raise ValueError('查詢模型與所選索引簽章不符，未搜尋或重建')
        from Code_2.functions.qa.question_bank import query_vector
        def generate_query():
            vector = (provider.embed_query(question) if backend == 'voyage' else
                      provider.embed([question], batch_size=1)[0])
            usage = getattr(provider, 'last_query_usage', {})
            return vector, usage if isinstance(usage, dict) else {}
        vector, query_usage, cache = query_vector(settings, question, provider.profile, generate_query)
        base['query_embedding'] = {'model': provider.profile,
                                   'usage': query_usage, 'cache': cache}
        base['completed_stages'].append('query_embedding')
        observe('query_embedding', elapsed_seconds=time.perf_counter()-phase_started, provider=provider)
        stage = 'retrieval'
        store = store_factory(settings.vector_root / backend, signature=signature, create=False)
        if store.collection_name != index['collection']:
            raise ValueError('所選collection簽章錯配')
        phase_started = time.perf_counter()
        raw_rows = store.search(vector, n_results=qa.retrieve_k, where=where)
        retrieval_seconds = time.perf_counter()-phase_started
        phase_started = time.perf_counter()
        heading_parent = qa.include_heading_parent and not is_original
        sources = evidence_rows(raw_rows, include_heading_parent=heading_parent)
        observe('retrieval', rows=raw_rows, sources=sources, elapsed_seconds=retrieval_seconds,
                parent_expansion_seconds=time.perf_counter()-phase_started)
        base['retrieved_evidence'] = sources
        base['retrieval'] = [{'chunk_id': s['chunk_id'], 'rank': s['retrieval_rank'],
                              'distance': s['retrieval_distance']} for s in sources]
        base['completed_stages'].append('retrieval')
        if not sources:
            if mode != 'answer':
                return {**base, 'status': 'no_results', 'message': '指定索引與篩選範圍沒有可用候選，未執行後續階段。'}
            return {**base, 'status': 'insufficient_evidence', 'answer': {
                'status': 'insufficient_evidence', 'reason': '指定索引與篩選範圍沒有可用證據。',
                'claims': [], 'calculations': []}}
        if mode == 'retrieve':
            selected_rows = raw_rows[:qa.evidence_k]
            base['selected_child_ids'] = [row['chunk_id'] for row in selected_rows]
            base['evidence_selection'] = 'retrieval_children_then_parent'
            base['evidence'] = evidence_rows(selected_rows, include_heading_parent=heading_parent)
            return {**base, 'status': 'retrieved'}
        if need_rerank:
            stage = 'rerank'
            phase_started = time.perf_counter()
            selected, usage = reranker.rerank(question, sources)
            observe('rerank', sources=selected, elapsed_seconds=time.perf_counter()-phase_started)
            base.update(evidence=selected, rerank=usage)
            base['completed_stages'].append('rerank')
        else:
            selected = sources[:qa.evidence_k]
            base.update(evidence=selected, evidence_selection='retrieval_top_k')
        if mode == 'rerank':
            return {**base, 'status': 'reranked'}
        stage = 'answer'
        if qa.answer_provider == 'gemini':
            base['answer_system_prompt'] = gemini_prompt(qa.gemini_system_prompt)
            if qa.gemini_system_prompt is not None:
                base['prompt_version'] = 'evidence-answer/custom'
        try:
            phase_started = time.perf_counter()
            answer, usage = answerer.answer(question, selected)
            observe('answer', elapsed_seconds=time.perf_counter()-phase_started)
        finally:
            attempt = getattr(answerer, 'last_attempt', None)
            if isinstance(attempt, dict):
                base['generation'] = dict(attempt)
        base['generation'] = usage
        stage = 'validate_answer'
        answer = validate_answer(answer, selected)
        base['completed_stages'].append('answer')
        return {**base, 'status': answer['status'], 'answer': answer}
    except KeyboardInterrupt:
        return {**base, 'status': 'failed', 'stage': stage, 'error': '使用者中止；未重試'}
    except Exception as error:
        # 只有本模組明確建立的安全訊息可顯示；第三方例外不含body／原題／密鑰。
        from Code_2.functions.qa.bge_reranker import BgeRerankError
        safe = isinstance(error, BgeRerankError) or (isinstance(error, (ValueError, RuntimeError)) and type(error).__module__ == 'builtins')
        message = str(error) if safe and stage not in ('query_embedding', 'retrieval') else type(error).__name__
        return {**base, 'status': 'failed', 'stage': stage, 'error': message}
    finally:
        if store is not None:
            store.close()
        if client is not None:
            # SDK 0.5.0沒有公開close；不碰私人屬性，client限本次問答生命週期。
            close = getattr(client, 'close', None)
            if callable(close):
                close()
