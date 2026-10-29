"""EXPERIMENT_ONLY：集中寫prepared與問答檢查產物；停用不影響核心。

移除時調整embedding/batch.py與qa/run.py的呼叫、output_dir／response_dir設定。
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

TAIPEI = timezone(timedelta(hours=8), 'Asia/Taipei')


def response_roots(settings):
    return [settings.response_dir] + [settings.project_root / 'Output' / ('reponse_' + role)
                                      for role in ('embedding', 'rerank', 'answer')]


def reserve_qa_run(settings, *, now=None, mode=None):
    """EXPERIMENT_ONLY：API前保留本題目錄，碰撞即停；不寫問題或金鑰。"""
    if not settings.export_enabled:
        return None
    instant = now or datetime.now(TAIPEI)
    if instant.tzinfo is None:
        raise ValueError('問答時間必須含時區')
    instant = instant.astimezone(TAIPEI)
    roles = {'retrieve': 'embedding', 'rerank': 'rerank', 'answer': 'answer'}
    root = settings.project_root / 'Output' / ('reponse_' + roles[mode]) if mode in roles else settings.response_dir
    target = root / ('qa_' + instant.strftime('%Y%m%d_%H-%M-%S_%f'))
    target.mkdir(parents=True, exist_ok=False)
    return {'json': target / 'result.json', 'markdown': target / 'answer.md',
            'created_at': instant.isoformat(), 'project_root': settings.project_root}


def export_qa_run(settings, paths, result):
    """EXPERIMENT_ONLY：整題成功／不足／失敗皆保存；寫檔失敗清理本次半份檔。"""
    if not settings.export_enabled:
        return None
    from Code_2.functions.qa.answers import render_qa_report
    expected = {p.resolve() for p in response_roots(settings)}
    target = paths['json'].parent.resolve()
    if (target.parent not in expected or paths['json'].name != 'result.json' or
            paths['markdown'].parent.resolve() != target or paths['markdown'].name != 'answer.md'):
        raise ValueError('問答輸出路徑超出指定範圍')
    check_paths({key: paths[key] for key in ('json', 'markdown')})
    saved = {**result, 'created_at': paths['created_at']}
    payloads = {paths['json']: json.dumps(saved, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'),
                paths['markdown']: render_qa_report(saved).encode('utf-8')}
    if 'project_root' in paths:
        from Code_2.functions.experiments.question_reports import payloads as question_payloads
        payloads.update(question_payloads(paths, saved))
    created = []
    try:
        for path, data in payloads.items():
            with path.open('xb') as stream:
                created.append(path)
                stream.write(data)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return target


def output_paths(settings, batch_name, prefix):
    target = settings.output_dir / batch_name
    return {'json': target / f'{prefix}_prepared.json',
            'markdown': target / f'{prefix}_prepared.md',
            'record': target / 'Record' / f'{prefix}_reocrd'}


def check_paths(paths):
    for path in paths.values():
        if path.exists():
            raise FileExistsError(f'輸出已存在，未覆寫：{path}')


def export_prepared(settings, paths, record, result):
    if not settings.export_enabled:
        return None
    from Code_2.functions.embedding.prepare import render_prepared
    check_paths(paths)
    paths['record'].parent.mkdir(parents=True, exist_ok=True)
    payloads = {}
    if result is not None:
        payloads = {'json': json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'),
                    'markdown': render_prepared(result).encode('utf-8')}
        record['outputs'] = {k: {'filename': paths[k].name, 'sha256': hashlib.sha256(v).hexdigest()}
                             for k, v in payloads.items()}
    created = []
    try:
        for role, data in payloads.items():
            with paths[role].open('xb') as stream:
                created.append(paths[role])
                stream.write(data)
        with paths['record'].open('x', encoding='utf-8') as stream:
            created.append(paths['record'])
            json.dump(record, stream, ensure_ascii=False, indent=2)
    except (OSError, KeyboardInterrupt) as error:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        record.pop('outputs', None)
        record.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                      error=f'輸出未完成：{type(error).__name__}')
        # 若磁碟本身無法寫紀錄，讓例外繼續回報，不假裝留下成功紀錄。
        with paths['record'].open('x', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
    return paths['json'].parent
