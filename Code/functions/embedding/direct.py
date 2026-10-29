"""第五階段：chunk JSON → 記憶體前處理 → 向量庫，不輸出prepared檔。"""
import hashlib
import json
import time
from pathlib import Path
from Code.functions.embedding.prepare import prepare_document
from Code.functions.embedding.fields import load_rules, select_fields
from Code.functions.embedding.providers import create_provider
from Code.functions.embedding.indexing import build_document, save_attempt
from Code.functions.embedding.store import ChromaStore
from Code.functions.embedding.paths import batch_location
from Code.functions.chunking.filenames import parse_chunk_filename, validate_chunk_filename


def build_files(sources, settings, *, backend, check_only=False,
                provider_factory=create_provider, store_class=ChromaStore, progress=None, control_id=None,
                index_target=None, batch_prefix=None):
    if batch_prefix is not None:
        from Code.functions.embedding.index_target import validate_choice
        validate_choice('batch', batch_prefix)
        if index_target is not None:
            raise ValueError('批次建庫不可同時指定單一索引')
    if backend not in ('bge', 'voyage'):
        raise ValueError('請選擇BGE或Voyage')
    if backend == 'voyage' and not settings.allow_voyage_api:
        raise ValueError('使用Voyage前請明確啟用API')
    if type(check_only) is not bool:
        raise ValueError('只檢查設定須為布林值')
    sources = [Path(p) for p in sources]
    if not sources or len(set(sources)) != len(sources):
        raise ValueError('請選擇不重複的chunk JSON')
    if control_id is not None:
        from Code.functions.embedding.job_control import read_control
        control=read_control(settings,control_id)
        if control['files'] != [p.resolve().relative_to(settings.input_dir.resolve()).as_posix() for p in sources]:
            raise ValueError('建庫控制清單與本次來源不符')
    rules = load_rules(settings.fields_file)
    rules_file_sha = hashlib.sha256(settings.fields_file.read_bytes()).hexdigest()
    provider, outcomes, identities = None, [], set()
    # 來源範圍、模式與身分先整批預檢；避免選錯檔案才開始下載或使用API。
    plans = []
    source_keys, group_specs = {}, {}
    planned_signatures = set()
    for source_index, source in enumerate(sources):
        if progress and batch_prefix is not None:
            progress({'current':f'預檢來源 {source_index+1}/{len(sources)}：{source.name}'})
        if source.is_symlink() or parse_chunk_filename(source.name) is None:
            raise ValueError('來源必須是chunk JSON，且不可為連結')
        _, mode, _ = batch_location(source.parent, settings.input_dir)
        issue, digest, identity = None, None, None
        try:
            raw = source.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            doc = json.loads(raw.decode('utf-8'))
            prepared = prepare_document(doc, input_sha256=digest)
            if mode and doc.get('chunking', {}).get('mode') != mode:
                raise ValueError('來源資料夾與切分模式不符')
            from Code.functions.embedding.index_target import plan_key
            key = plan_key(prepared)
            first = prepared['chunks'][0]['metadata']
            validate_chunk_filename(source.name, doc, first['stock_code'])
            for item in prepared['chunks']:
                select_fields(item, rules)
            identity = (doc['doc_id'], key)
            planned_signatures.add(key)
            source_keys[source] = key
            group_specs.setdefault(key, prepared.get('chunking', {}))
        except Exception as error:
            issue = str(error) if type(error) is ValueError else f'{type(error).__name__}：來源JSON驗證失敗'
        if identity is not None:
            if identity in identities:
                raise ValueError('同一索引的doc_id重複，請分開選取')
            identities.add(identity)
        plans.append((source, digest, issue))
    if index_target is not None and (len(planned_signatures) != 1 or any(issue for _,_,issue in plans)):
        raise ValueError('一個自訂索引只能加入同一切法、字數與處理版本的有效來源；請分批新建索引')
    targets, group_info = {}, {}
    if batch_prefix is not None:
        from Code.functions.embedding.index_target import resolve_target
        for number, (key, spec) in enumerate(group_specs.items(), 1):
            modes = json.loads(key).get('embedding_context_modes') or {}
            suffix = (f" · G{number} {spec.get('mode','legacy')}_{spec.get('recursive_threshold','legacy')}"
                      f" · text-{modes.get('text','legacy')}_table-{modes.get('table','legacy')}")
            name = batch_prefix.strip()[:max(1,80-len(suffix))] + suffix
            targets[key] = resolve_target(settings, backend, mode='new', name=name)
            group_info[key] = {'group_number':number,'group_total':len(group_specs),'index_group_name':name}
        plans.sort(key=lambda p:group_info.get(source_keys.get(p[0]),{}).get('group_number',len(group_specs)+1))
        if progress:
            progress({'group_total':len(group_specs),
                      'embedding_files':[p.resolve().relative_to(settings.input_dir.resolve()).as_posix() for p,_,_ in plans]})
    attempted=[]
    for index, (source, digest, issue) in enumerate(plans):
        if control_id is not None:
            control=read_control(settings,control_id)
            if control['stop_requested'] and (control['stop_after'] is None or control['stop_after'] in attempted):
                if progress:
                    progress({'state':'stopped','completed':index,'total':len(plans),
                              'stop_after':control['stop_after'],'skipped':[p.relative_to(settings.input_dir).as_posix() for p,_,_ in plans[index:]]})
                break
        started, opened = time.perf_counter(), []
        record = {'schema_version': 'embedding-index-run/1.0', 'backend': backend,
                  'source_file': source.name, 'status': 'failed',
                  'stage': 'source_validation', 'check_only': check_only,
                  'runtime_config': {'cpu_threads': settings.cpu_threads if backend == 'bge' else None,
                      'batch_size': settings.bge_batch_size if backend == 'bge' else settings.voyage_batch_size,
                      'batch_unit': 'chunk'}}
        group = group_info.get(source_keys.get(source),
            {'group_number':None,'group_total':len(group_info),'index_group_name':'來源驗證失敗，未分組'} if batch_prefix is not None else {})
        record.update(group)
        if progress:
            progress({'current': source.name, 'current_id':source.resolve().relative_to(settings.input_dir.resolve()).as_posix(), 'completed': index, 'total': len(plans), **group})
        try:
            if issue:
                raise ValueError(issue)
            raw = source.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('來源在預檢後變更，未繼續該份建庫')
            doc = prepare_document(json.loads(raw.decode('utf-8')), input_sha256=digest)
            if 'embedding_context_modes' in doc:
                record['embedding_context_modes'] = doc['embedding_context_modes']
            record.update(doc_id=doc['doc_id'], stage='model_setup')
            if provider is None:
                provider = provider_factory(backend, settings)
            def verify():
                if (hashlib.sha256(source.read_bytes()).hexdigest() != digest or
                        hashlib.sha256(settings.fields_file.read_bytes()).hexdigest() != rules_file_sha):
                    raise ValueError('來源或欄位設定已變更，未提交')
            def open_store(signature):
                store = store_class(settings.vector_root / backend, signature=signature)
                opened.append(store)
                return store
            verify()
            record['stage'] = 'embedding_and_commit'
            record.update(build_document(doc, prepared_sha256=digest, rules=rules, provider=provider,
                batch_size=settings.bge_batch_size if backend == 'bge' else settings.voyage_batch_size,
                store_factory=open_store, check_only=check_only, before_commit=verify,
                index_target=targets.get(source_keys.get(source), index_target)))
            runtime = getattr(provider, 'runtime_config', None)
            if isinstance(runtime, dict):
                record['runtime_config'].update(runtime)
            record['stage'] = 'completed'
        except Exception as error:
            # 不輸出SDK例外body或金鑰；已知資料錯誤才顯示可讀原因。
            record.update(status='failed', error=str(error) if type(error) is ValueError else
                          f'{type(error).__name__}：模型或資料庫操作失敗，未宣稱已提交')
        finally:
            for store in reversed(opened):
                store.close()
        record['elapsed_seconds'] = round(time.perf_counter() - started, 6)
        if control_id is not None:
            record['job_id']=control_id
        if not check_only:
            save_attempt(settings.vector_root / backend, record)
        outcomes.append(record)
        attempted.append(source.resolve().relative_to(settings.input_dir.resolve()).as_posix())
        if progress:
            progress({'result': {'name': source.name, 'status': record['status'],
                **group,
                'message': record.get('error') or (f'{record.get("chunk_count", 0)} 塊；'
                    + ('超過模型token上限，整份未建庫' if record['status'] == 'blocked_token_limit' else
                       '已存在，略過' if record['status'] == 'already_indexed' else
                       '僅檢查，未建庫' if check_only else '已提交向量庫')),
                'collection': record.get('collection'), 'display_name':record.get('display_name'), 'stage': record['stage'],
                'elapsed_seconds': record['elapsed_seconds'],
                'runtime_config': record['runtime_config']}, 'completed': index + 1})
    if batch_prefix is not None and progress:
        summaries = []
        for key, info in group_info.items():
            rows = [r for r in outcomes if r.get('group_number') == info['group_number']]
            total = sum(source_keys.get(p) == key for p,_,_ in plans)
            succeeded = sum(r['status'] in ('indexed','checked','already_indexed') for r in rows)
            summaries.append({**info,'completed':len(rows),'total':total,'succeeded':succeeded,
                              'status':'stopped' if len(rows)<total else 'completed' if succeeded==total else 'completed_with_errors'})
        progress({'index_groups':summaries})
    return outcomes
