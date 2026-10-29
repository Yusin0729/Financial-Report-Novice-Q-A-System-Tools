"""網頁資料契約與唯讀紀錄；不提供任意檔案讀取／修改或金鑰查詢。"""
import re
from dataclasses import replace
from Code_2.config.embedding import BATCH_PATTERN
from Code_2.config.qa import QASettings, MODE_LABELS
from Code_2.functions.embedding.indexing import recent_attempts
from Code_2.functions.qa.catalog import list_indexes
from Code_2.functions.embedding.paths import locations

RUN_PATTERN = r'(?:qa_\d{8}_\d{2}-\d{2}-\d{2}_\d{6}|(?:BGE|Voyage) (?:父子250|原始))'


def batch_names(root):
    if not root.is_dir():
        return []
    return sorted((p.relative_to(root).as_posix() for p in locations(root)), reverse=True)


def metadata(settings, web):
    from Code_2.functions.qa.rerankers import local_profiles
    qa = QASettings()
    from Code.functions.embedding.api_settings import public_settings
    return {'api_settings': public_settings(settings.project_root), 'indexes': list_indexes(settings),
            'defaults': {'retrieve_k': qa.retrieve_k, 'evidence_k': qa.evidence_k,
                         'max_retrieve_k': qa.max_retrieve_k, 'export_enabled': settings.export_enabled,
                         'backend': settings.default_backend},
            'models': {'rerank': qa.rerank_model, 'answer': qa.answer_model},
            'local_rerank_profiles': local_profiles(),
            'poll_milliseconds': web.poll_milliseconds}


def boolean(data, key, default=False):
    value = data.get(key, default)
    if type(value) is not bool:
        raise ValueError(f'{key}必須為布林值')
    return value


def integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}須為{low}至{high}的整數')
    return value


def validate_task(data, settings):
    if not isinstance(data, dict):
        raise ValueError('請求須為物件')
    action = data.get('action')
    if action == 'rerank-report':
        # EXPERIMENT_ONLY：只使用舊報告候選，與正式ask隔離。
        from Code_2.functions.experiments.saved_rerank import validate_task as validate_saved
        return validate_saved(data, settings)
    if action == 'make-charts':
        from Code_2.functions.experiments.chart_report import validate_source
        return {'action':action,'source':validate_source(data,settings)}
    if 'indexes' in data:
        if action not in ('query','evaluate'):
            raise ValueError('只有查詢及Excel測試支援複選索引')
        indexes=data['indexes']
        if not isinstance(indexes,list) or not 1<=len(indexes)<=20:
            raise ValueError('請選1至20個不重複索引')
        base={k:v for k,v in data.items() if k not in ('indexes','backend','collection')}
        tasks=[];seen=set()
        for item in indexes:
            if not isinstance(item,dict) or set(item)!={'backend','collection'}:
                raise ValueError('索引清單格式無效')
            clean=validate_task({**base,**item},settings)
            key=(clean['backend'],clean['collection'])
            if key in seen:raise ValueError('索引不可重複')
            seen.add(key);tasks.append(clean)
        return {**tasks[0],'indexes':[{'backend':t['backend'],'collection':t['collection']} for t in tasks],
                **({'embedding_profile':data['embedding_profile']} if data.get('embedding_profile') else {})}
    if action in ('prepare', 'embed'):
        raise ValueError('前處理與建庫已移至Code網頁第五階段')
    if action == 'evaluate':
        # EXPERIMENT_ONLY：整段移除即停用批次，不改一般query契約。
        from Code_2.config.evaluation import EvaluationSettings
        if not EvaluationSettings().enabled:
            raise ValueError('Excel實驗功能已停用')
        extra = {'workbook_base64', 'filename', 'sheet', 'ids', 'generate_charts'}
        query = {k:v for k,v in data.items() if k not in extra}
        query.update(action='query', question='Excel批次驗證', stock_code=None, report_year=None)
        if 'question' in data or 'stock_code' in data or 'report_year' in data:
            raise ValueError('Excel批次的問題與篩選只讀各題欄位')
        clean = validate_task(query, settings)
        from Code_2.functions.experiments.eval_run import selected_rows
        book, rows = selected_rows(data)
        clean = {k:v for k,v in clean.items() if k not in ('question','stock_code','report_year')}
        clean.update(action='evaluate', workbook_base64=data['workbook_base64'], filename=data['filename'],
                     sheet=book['sheet'], ids=[r['ID'] for r in rows],
                     generate_charts=boolean(data,'generate_charts',False))
        return clean
    common = {'action', 'export_enabled'}
    allowed = {'query': common | {'question', 'backend', 'collection', 'stock_code', 'report_year',
                                  'mode', 'retrieve_k', 'evidence_k', 'embedding_profile', 'rerank_profile', 'answer_profile', 'rerank_enabled','include_heading_parent'}}
    if not isinstance(action, str) or action not in allowed or set(data) - allowed[action]:
        raise ValueError('不支援的操作或欄位')
    clean = {'action': action}
    if action in ('prepare', 'query'):
        clean['export_enabled'] = boolean(data, 'export_enabled', settings.export_enabled)
    if action == 'query':
        question = data.get('question')
        qa = QASettings()
        if not isinstance(question, str) or not question.strip() or len(question) > qa.max_question_characters:
            raise ValueError('請輸入有效問題，長度不得超過設定上限')
        mode = data.get('mode')
        if not isinstance(mode, str) or mode not in MODE_LABELS:
            raise ValueError('請選擇執行模式')
        clean['rerank_enabled'] = boolean(data, 'rerank_enabled', True)
        clean['include_heading_parent'] = boolean(data,'include_heading_parent',False)
        if mode == 'rerank' and not clean['rerank_enabled']:
            raise ValueError('到重排序模式必須啟用重排序')
        backend, collection = data.get('backend'), data.get('collection')
        if backend not in ('bge', 'voyage') or not isinstance(collection, str) or not re.fullmatch(r'financial_[a-f0-9]{24}', collection):
            raise ValueError('請選擇有效已建索引')
        stock, year = data.get('stock_code'), data.get('report_year')
        if stock is not None and (not isinstance(stock, str) or not re.fullmatch(r'[0-9]+', stock)):
            raise ValueError('股票代號須為數字字串，保留前導0')
        if year is not None:
            integer(year, '內容年度', 1900, 2199)
        retrieve = integer(data.get('retrieve_k'), '召回數量', 1, qa.max_retrieve_k)
        evidence = integer(data.get('evidence_k'), '重排序數量', 1, qa.max_retrieve_k)
        if mode != 'retrieve' and evidence > retrieve:
            raise ValueError('重排序數量不可大於召回數量，不會自動調整')
        from Code.functions.embedding.api_settings import resolve_profile
        for key, purpose in (('embedding_profile','embedding'), ('rerank_profile','rerank'), ('answer_profile','answer')):
            identity = data.get(key)
            if identity is not None:
                if not isinstance(identity,str) or not identity:
                    raise ValueError('請選擇有效API設定')
                if (purpose=='embedding' and backend=='voyage') or (purpose=='rerank' and mode!='retrieve' and clean['rerank_enabled']) or (purpose=='answer' and mode=='answer'):
                    if purpose == 'rerank':
                        from Code_2.functions.qa.rerankers import resolve_rerank_profile
                        resolve_rerank_profile(settings.project_root, identity)
                    else:
                        resolve_profile(settings.project_root, identity, purpose)
                    clean[key] = identity
        clean.update(question=question, backend=backend, collection=collection, mode=mode,
                     stock_code=stock, report_year=year, retrieve_k=retrieve, evidence_k=evidence)
    return clean


def execute_task(data, settings):
    """在獨立worker內使用既有核心；不改其輸入、失敗與提交契約。"""
    action = data['action']
    if action=='rerank-report':
        from Code_2.functions.experiments.saved_rerank import run
        return run(data, settings, progress=lambda message: print(message, flush=True))
    if action=='make-charts':
        from Code_2.functions.experiments.chart_report import make_report
        return {'action':action,'evaluation':make_report(data['source'],settings)}
    if 'indexes' in data:
        from Code_2.functions.web.comparison import run_comparison
        return run_comparison(data,settings,execute_task)
    if action in ('prepare', 'embed'):
        raise ValueError('前處理與建庫已移至Code網頁第五階段')
    from Code_2.functions.qa.run import run_question
    # 單題run_question只回傳結果；批次報告由獨立實驗模組保存。
    qa = replace(QASettings(), retrieve_k=data['retrieve_k'], evidence_k=data['evidence_k'],
                 rerank_profile=data.get('rerank_profile'), answer_profile=data.get('answer_profile'),
                 rerank_enabled=data.get('rerank_enabled', True),
                 include_heading_parent=data.get('include_heading_parent',False))
    current = replace(settings, export_enabled=data['export_enabled'], embedding_profile=data.get('embedding_profile'))
    if action == 'evaluate':
        # EXPERIMENT_ONLY：批次逐題核心及報告可整段移除。
        from Code_2.functions.experiments.eval_run import run_batch
        result = run_batch(data, current, qa, progress=lambda message: print(message, flush=True))
        return {'action': action, 'evaluation': result}
    result = run_question(data['question'], current, backend=data['backend'], collection=data['collection'],
                          mode=data['mode'], stock_code=data['stock_code'], report_year=data['report_year'], qa=qa)
    return {'action': action, 'query': result}


def task_outcome(result):
    if result.get('multi'):
        return 'completed' if all(r.get('outcome')=='completed' for r in result['results']) else 'needs_attention'
    if result['action']=='make-charts':
        return 'completed' if result['evaluation'].get('export_status')=='saved' else 'needs_attention'
    if result['action'] == 'evaluate':
        row=result['evaluation']
        return 'needs_attention' if row.get('export_status')=='failed' or row['status']!='completed' else 'completed'
    if result['action'] == 'query':
        row = result['query']
        if row['status'] == 'failed' or row.get('export_status') == 'failed':
            return 'failed'
        return 'completed'
    rows = result['rows']
    success = {'prepared_needs_review', 'indexed', 'already_indexed', 'checked'}
    if not rows or any(row['status'] not in success for row in rows):
        return 'needs_attention'
    return 'completed'


def report_path(settings, name, filename):
    if not isinstance(name, str) or not re.fullmatch(RUN_PATTERN, name) or filename not in ('answer.md', 'result.json', 'results.xlsx', 'charts.svg'):
        raise ValueError('紀錄名稱無效')
    from Code_2.functions.experiments.export_output import response_roots
    matches = [root / name for root in response_roots(settings) if (root / name).is_dir()]
    if len(matches) != 1:
        raise FileNotFoundError('紀錄不存在或名稱不唯一')
    folder = matches[0]
    root = folder.parent.resolve()
    path = folder / filename
    if folder.is_symlink() or path.is_symlink() or folder.resolve().parent != root or path.resolve().parent != folder.resolve():
        raise ValueError('紀錄路徑超出指定目錄')
    if not path.is_file():
        raise FileNotFoundError('紀錄不存在或尚未完成保存')
    return path


def reports(settings, web):
    from Code_2.functions.experiments.export_output import response_roots
    names = sorted({p.name for root in response_roots(settings) if root.is_dir()
                    for p in root.iterdir() if re.fullmatch(RUN_PATTERN, p.name)}, reverse=True)
    output = []
    for name in names:
        try:
            path = report_path(settings, name, 'answer.md')
            output.append({'name': name, 'bytes': path.stat().st_size, 'has_excel': (path.parent/'results.xlsx').is_file()})
        except (ValueError, FileNotFoundError):
            continue
        if len(output) >= web.history_limit:
            break
    return output


def history(settings, web):
    return {'reports': reports(settings, web),
            'index_attempts': {name: recent_attempts(settings, name) for name in ('bge', 'voyage')}}
