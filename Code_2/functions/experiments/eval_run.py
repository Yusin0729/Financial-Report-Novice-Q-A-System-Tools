"""EXPERIMENT_ONLY：Excel逐題測試，單次集合與設定；正式問答不依賴此模組。"""
import hashlib
import base64
import json
import time
from dataclasses import replace
from statistics import mean
from Code_2.config.evaluation import EvaluationSettings
from Code_2.functions.qa.pipeline import ask
from Code_2.functions.qa.catalog import list_indexes,select_index
from Code_2.functions.embedding.providers import create_provider
from Code_2.functions.experiments.eval_workbook import read_upload,write_xlsx
from Code_2.functions.experiments.eval_scoring import score,doc_identity,TITLE_RULE,NUMERIC_RULE,SUPPORTED_RULES
from Code_2.functions.experiments.eval_curve import build_curves
from Code_2.functions.experiments.export_output import reserve_qa_run


def selected_rows(data):
    book=read_upload(data.get('workbook_base64'),data.get('filename'),data.get('sheet'))
    ids=data.get('ids')
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('請勾選不重複的題目ID')
    available={r['ID']:r for r in book['rows'] if not r['errors'] and not r['excluded']}
    if not set(ids).issubset(available):raise ValueError('所選ID無效、已排除或題目欄位有錯')
    return book,[r for r in book['rows'] if r['ID'] in ids]

def _candidates(evidence,lookup):
    result=[]
    for rank,e in enumerate(evidence,1):
        chunk=lookup.get(e['chunk_id'])
        if chunk is None:raise ValueError('召回結果缺少可評分的原始chunk')
        result.append({'chunk':chunk,'text':e['text'],'rank':e.get('rerank_rank',e.get('retrieval_rank',rank)),
                       'matched_chunk_ids':e['matched_chunk_ids'],'parent_relation':e.get('parent_relation')})
    return result

def _counter(settings):
    try:
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(settings.bge_model,revision=settings.bge_revision,
            cache_dir=str(settings.model_cache),local_files_only=True,trust_remote_code=False)
        return lambda texts:sum(len(tokenizer.encode(t,add_special_tokens=False,truncation=False)) for t in texts)
    except (ImportError,OSError):return None

def run_batch(data,settings,qa,*,ask_function=ask,provider_factory=create_provider,index=None,progress=None,token_counter=None):
    book,questions=selected_rows(data)
    index=index or select_index(list_indexes(settings,data['backend']),data['backend'],data['collection'])
    cfg=EvaluationSettings();started=time.perf_counter()
    paths=reserve_qa_run(settings, mode=data['mode'])  # EXPERIMENT_ONLY：API前確保新報告目錄可建立。
    result={'schema_version':'financial-evaluation/1.0','scoring_rule':(NUMERIC_RULE if any(r.get('numeric_targets') for r in questions) else TITLE_RULE),
        'filename':book['filename'],'sheet':book['sheet'],'source_sha256':hashlib.sha256(base64.b64decode(data['workbook_base64'])).hexdigest(),
        'settings':{'retrieve_k':qa.retrieve_k,'evidence_k':qa.evidence_k,
                    **{k:v for k,v in data.items() if k not in ('workbook_base64','ids')}},
        'index':index,'excluded_ids':list(cfg.excluded_ids),'rows':[],
        'tokenizer':{'model':settings.bge_model,'revision':settings.bge_revision,'meaning':'僅作跨方法內容長度比較，非API計費tokens'},
        'status':'completed'}
    current=replace(settings,export_enabled=False)
    cached={};stopped=False
    def provider(backend,s):
        if backend not in cached:cached[backend]=provider_factory(backend,s)
        return cached[backend]
    count=token_counter if token_counter is not None else _counter(settings)
    if count is None:result['tokenizer']['status']='本機tokenizer未快取，內容tokens未知；未下載'
    try:
        for number,row in enumerate(questions,1):
            if progress:progress(f"批次測試 {number}/{len(questions)}：ID {row['ID']}")
            entry={'ID':row['ID'],'Question':row['Question'],'reference':row,'status':'not_run'}
            result['rows'].append(entry)
            if stopped:
                entry['error']='前題外部服務／執行失敗，為避免重複費用停止後續題目';continue
            if row['stock_code'] and not any((doc_identity(d) or (None,None))[1]==row['stock_code'] for d in index['doc_ids']):
                entry.update(status='corpus_unavailable',error='所選索引沒有該股號的已提交文件')
                continue
            trace={};lookup={};timings={}
            def observe(name,values):
                timings[name]=round(values['elapsed_seconds'],6)
                if name=='retrieval':
                    trace['raw_rows']=values['rows'];trace['returned']=values['sources']
                    timings['parent_expansion']=round(values['parent_expansion_seconds'],6)
                    for r in values['rows']:
                        for field in ('original_chunk','original_parent','original_heading_parent'):
                            chunk=r['payload'].get(field)
                            if chunk is not None:lookup[chunk['chunk_id']]=chunk
                elif name=='rerank':trace['rerank']=values['sources']
            before=time.perf_counter()
            query=ask_function(row['Question'],current,backend=data['backend'],collection=data['collection'],
                mode=data['mode'],stock_code=row['stock_code'],report_year=row['filter_years'] or None,
                qa=qa,index=index,provider_factory=provider,observer=observe)
            entry.update(status=query['status'],query=query,timings=timings,
                         elapsed_seconds=round(time.perf_counter()-before,6),cold_query=number==1)
            raw=[{'chunk':r['payload']['original_chunk'],'rank':i,'text':r['payload'].get('embedding_text','')}
                 for i,r in enumerate(trace.get('raw_rows',[]),1)]
            # EXPERIMENT_ONLY：保存原始Top K子項，分題重排輸入不再靠索引還原。
            query['retrieved_children']=[{'id':f'C{i}','chunk_id':c['chunk']['chunk_id'],
                'doc_id':c['chunk']['doc_id'],'page':c['chunk'].get('page',[]),
                'years':c['chunk'].get('years',[]),'text':c['text'],'retrieval_rank':i,
                'parent_id':c['chunk'].get('parent_id'),'parent_relation':c['chunk'].get('parent_relation'),
                'input_sha256':trace['raw_rows'][i-1]['payload'].get('input_sha256')}
                for i,c in enumerate(raw,1)]
            returned=_candidates(trace.get('returned',[]),lookup)
            reranked=_candidates(trace.get('rerank',[]),lookup)
            entry['scores']={'retrieval':score(row,raw,retrieve_k=qa.retrieve_k),'returned':score(row,returned,retrieve_k=qa.retrieve_k)}
            if 'rerank' in trace:entry['scores']['rerank']=score(row,reranked,retrieve_k=qa.retrieve_k)
            entry['score_stage']='rerank' if 'rerank' in trace else 'returned'
            entry['score']=entry['scores'][entry['score_stage']]['score']
            entry['weighted_score']=entry['score']
            entry['raw_score']=entry['scores'][entry['score_stage']]['raw_score']
            entry['raw_top20_chunk_ids']=[c['chunk']['chunk_id'] for c in raw[:cfg.top_k]]
            entry['usage']={'query_embedding':query.get('query_embedding',{}).get('usage',{}),
                'rerank':query.get('rerank',{}),'generation':query.get('generation',{})}
            entry['content_tokens']={}
            for name,candidates in (('retrieval',raw),('returned',returned),('rerank',reranked)):
                entries=entry['scores'].get(name,{}).get('top20',[])
                entry['content_tokens'][name]=count([c['text'] for c in entries]) if count else None
            if query['status']=='failed':
                entry['error']=query.get('error','查詢失敗');stopped=True;result['status']='needs_attention'
    except (Exception,KeyboardInterrupt) as e:
        result.update(status='failed',error=f'批次中斷（{type(e).__name__}），保留已完成題目；未重試')
    finally:
        for p in cached.values():
            close=getattr(getattr(p,'client',None),'close',None)
            if callable(close):close()
    result['elapsed_seconds']=round(time.perf_counter()-started,6)
    completed=[r for r in result['rows'] if r.get('score') is not None and r['status']!='failed']
    result['summary']={'selected':len(questions),'scored':len(completed),
        'mean_score':round(mean(r['score'] for r in completed),4) if completed else None,
        'mean_weighted_score':round(mean(r['score'] for r in completed),4) if completed else None,
        'mean_raw_score':round(mean(r['raw_score'] for r in completed),4) if completed else None,
        'unavailable':sum(r['status']=='corpus_unavailable' for r in result['rows']),
        'failed':sum(r['status']=='failed' for r in result['rows']),
        'not_run':sum(r['status']=='not_run' for r in result['rows'])}
    if any(r['status'] in ('corpus_unavailable','failed','not_run') for r in result['rows']) and result['status']=='completed':result['status']='needs_attention'
    result['charts_requested']=data.get('generate_charts',False)
    result['curves']={};result['raw_curves']={}
    if result['charts_requested']:
        result['curves']=build_curves(result['rows'],qa.retrieve_k)
        result['raw_curves']=build_curves(result['rows'],qa.retrieve_k,metric='raw')
    if paths is None:result['export_status']='disabled'
    else:
        # EXPERIMENT_ONLY：唯一批次報告寫檔呼叫；停用時純查詢／評分仍可執行。
        try:
            result.update(export_status='saved',output_dir=str(paths['json'].parent),created_at=paths['created_at'])
            export_batch(paths,result)
        except (OSError,ValueError,TypeError) as e:
            result.update(export_status='failed',export_error=f'批次報告保存失敗（{type(e).__name__}），不可視為完整保存')
    return result

def render_report(result):
    lines=['# Excel批次證據測試',f"來源：{result['filename']}／{result['sheet']}",
        f"狀態：{result['status']}；題數：{len(result['rows'])}；總耗時：{result.get('elapsed_seconds')}秒",
        f"平均得分：{result.get('summary',{}).get('mean_score') if result.get('summary',{}).get('mean_score') is not None else '無法計分'} / 10；計入平均：{result.get('summary',{}).get('scored',0)}題（未命中0分仍計入；失敗、未執行或無法評分不計入）。",
        ('股號與內容年度須符合；來源財報年度不限。標題移除開頭編號後比對Sub_Section或Note_Title各層完整名稱；Page只供核對，不擋得分。'
         if result.get('scoring_rule') in SUPPORTED_RULES[1:] else '來源沿用舊版評分：文件年度與內容年度須符合，完整標題與標準頁碼須在同一chunk；不按新版重算。'),
        f"評分規則：{result.get('scoring_rule')}",
        '每個年度×標題為一項，各占10/N分；原始分數按命中比例。新版排名加權每晚於理想名次一名扣「該項配分/K」，舊報告保留原扣分，以各階段scoring_rule及rank_penalty為準。年度空白則每標題一項；有必要數字標註者須同時命中數字。重排沿用檢索K。',
        f"原始平均得分：{result.get('summary',{}).get('mean_raw_score')} / 10；排名加權平均得分：{result.get('summary',{}).get('mean_weighted_score')} / 10",
        '內容token數使用同一BGE tokenizer，與供應商計費用量分開。錯誤／語料缺漏不假裝成功。']
    if result.get('report_kind')=='saved_rerank':
        lines.extend([f"舊報告重排序；來源：{result.get('source_run')}",
            '只呼叫重排序API；原始檢索／父項召回後評分為來源基準，不是本次重新檢索結果。',
            '本次只保留所選數量的重排證據；評分排名扣分分母仍沿用來源檢索K。'])
    if result.get('report_kind')=='chart_statistics':
        lines.extend([f"圖表統計另存報告；來源：{result.get('source_run') or '畫面上未保存的評分結果'}",'![原始與排名加權折線圖](charts.svg)'])
    all_curves=[('排名加權',result.get('curves',{})),('原始',result.get('raw_curves',{}))]
    for kind,stage,curve in [(kind,stage,c) for kind,curves in all_curves for stage,c in curves.items()]:
        lines.extend(['',f'## {kind}平均得分曲線：{stage}',
            f"計入{curve['count']}題；每項每名扣分：{curve['rank_penalty'] if curve['rank_penalty'] is not None else '依各題配分，見逐題明細'}。{curve['meaning']}",
            f"本次達完整平均分的最小有效Top：{curve['first_full_score_k'] or '無法建議（全部零分）'}",
            '|有效Top K|平均得分|增加分數|','|---|---|---|'])
        for p in curve['points']:lines.append(f"|{p['k']}|{p['mean_score']}|{p['gain']}|")
        lines.extend(['|區塊|區塊末平均得分|區塊增分|','|---|---|---|'])
        for b in curve['blocks']:lines.append(f"|{b['start']}–{b['end']}|{b['mean_score']}|{b['gain']}|")
    for row in result['rows']:
        lines.extend(['',f"## ID {row['ID']}",row['Question'],f"狀態：{row['status']}；耗時：{row.get('elapsed_seconds','未執行')}秒"])
        reference = row.get('reference') or {}
        if reference.get('Evidence_Type'):
            lines.append('標準證據類型：'+reference['Evidence_Type']+'；跨頁表格：'+(reference.get('Cross_Page_Table') or 'unknown'))
        cache = row.get('query', {}).get('query_embedding', {}).get('cache')
        if cache is not None:
            lines.append('問題向量題庫：' + ('命中快取，本次未重新向量化' if cache['hit'] else '未命中，已產生並保存向量'))
        if row.get('error'):lines.append('原因：'+row['error'])
        for stage,s in row.get('scores',{}).items():
            lines.extend([f"### {stage}：{s['score'] if s['score'] is not None else '無法計分'} / 10",
                f"原始分數：{s.get('raw_score')} / 10；排名加權分數：{s['score']} / 10；年度×標題命中：{s.get('target_coverage')}",
                '未找到年度×標題：'+('；'.join(s.get('missing_targets',[])) or '無'),
                '年度×標題命中Top：'+json.dumps(s.get('target_hits',{}),ensure_ascii=False),
                f"頁碼：{s['page_coverage']}；標題：{s['title_coverage']}",
                f"評分召回數：{s.get('retrieve_k')}；每名扣分：{s.get('rank_penalty')}",
                '未找到頁碼：'+('、'.join(s['missing_pages']) or '無'),
                '未找到標題：'+('；'.join(s['missing_titles']) or '無'),
                '標題命中排名：'+json.dumps(s['title_hits'],ensure_ascii=False),
                '本題評分規則：'+s.get('scoring_rule','來源舊版'),
                '必要數字標準：'+json.dumps(s.get('numeric_targets'),ensure_ascii=False),
                '評分備註：'+(s.get('scoring_note') or '無'),
                f"比較用內容tokens：{row.get('content_tokens',{}).get(stage)}",
                '| 有效Top | 原Top | chunk_id | 頁碼 | 命中標題 |','|---|---|---|---|---|'])
            for c in s['top20']:lines.append(f"|{c['effective_rank']}|{c['original_rank']}|{c['chunk_id']}|{c['page']}|{'；'.join(c['matched_titles'])}|")
        if result.get('report_kind') == 'saved_rerank':
            # EXPERIMENT_ONLY：重排保留證據逐筆全文，不截斷；原始候選仍在JSON。
            if result.get('candidate_unit') == 'child':
                lines.extend(['### 重排序Top子項全文（帶回父項之前）',
                    '輸入依chunk_id排序，不代表原檢索排名；TopK子項確定後才合併必回父項，不補選。'])
                for e in row.get('query', {}).get('reranked_children', []):
                    lines.extend([f"#### 子項Top {e['rerank_rank']}｜{e['chunk_id']}",
                        f"原檢索排名：{e.get('source_retrieval_rank') or '未知'}｜重排分數：{e['rerank_score']}｜必回父項：{e.get('return_evidence_id')}",
                        e.get('report_text', e['text'])])
            lines.append('### 最終回傳證據全文（同父項合併後）')
            for e in row.get('query', {}).get('evidence', []):
                lines.extend([f"#### Top {e['rerank_rank']}｜{e['chunk_id']}",
                    f"文件：{e['doc_id']}｜PDF頁序：{e['page']}｜{'首個命中子項分數' if e.get('rerank_score_scope') == 'best_selected_child' else '重排分數'}：{e['rerank_score']}",
                    f"父項關係：{e.get('parent_relation') or '無'}｜命中子項：{', '.join(e.get('matched_chunk_ids', []))}",
                    e.get('report_text', e['text'])])
    return '\n\n'.join(lines)+'\n'

def excel_report(result):
    # EXPERIMENT_ONLY：九頁報表只含作圖所需統計；全文保留result.json。
    from Code_2.functions.experiments.report_tables import build_tables
    source=result.get('output_dir') or result.get('source_run') or '本次結果'
    return write_xlsx(build_tables([(source,result)]),presentation=True)


def export_batch(paths,result):
    # 完整JSON先保存；衍生報表失敗也不丟失已完成的檢索。
    with paths['json'].open('xb') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'))
    try:
        _export_derived(paths,result)
    except (OSError,ValueError,TypeError) as error:
        saved={**result,'export_status':'partial',
               'export_error':f'衍生報告失敗（{type(error).__name__}）；完整JSON已保留，可離線重匯出'}
        paths['json'].write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
        raise


def _export_derived(paths,result):
    payloads={paths['markdown']:render_report(result).encode('utf-8'),
              paths['json'].with_name('results.xlsx'):excel_report(result)}
    if 'project_root' in paths and result.get('report_kind') != 'chart_statistics':
        from Code_2.functions.experiments.analysis_guide import render_analysis_guide
        from Code_2.functions.experiments.question_reports import payloads as question_payloads
        payloads[paths['json'].with_name('測試分析報告.md')] = render_analysis_guide(result).encode('utf-8')
        payloads.update(question_payloads(paths,result))
    created=[]
    try:
        for path,raw in payloads.items():
            with path.open('xb') as stream:created.append(path);stream.write(raw)
    except BaseException:
        for path in reversed(created):path.unlink(missing_ok=True)
        raise
