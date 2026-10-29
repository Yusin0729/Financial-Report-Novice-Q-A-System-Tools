"""網頁階段範圍協調；沿用單階段工作、輸出擁有權及建庫環境。"""
from collections import Counter
from pathlib import Path
import re
import time
import uuid
import hashlib

ORDER = ('raw', 'processed', 'tagged', 'chunk', 'embed')


def requested_stages(request):
    start = request.get('stage')
    end = request.get('end_stage', start)
    if start not in ORDER or end not in ORDER or ORDER.index(end) < ORDER.index(start):
        raise ValueError('執行範圍須為階段1至5，結束階段不可早於起始階段')
    return ORDER[ORDER.index(start):ORDER.index(end) + 1]


def validate_request(settings, request):
    from functions.web_ui.catalog import selected_paths
    from functions.web_ui.request_settings import request_settings
    stages = requested_stages(request)
    if type(request.get('final_output_only', False)) is not bool:
        raise ValueError('只保留最終產物設定須為布林值')
    if request.get('final_output_only'):
        if len(stages) < 2:
            raise ValueError('只保留最終產物適用於連續階段')
        if stages[-1] == 'embed' and request.get('check_only'):
            raise ValueError('只檢查 token 不建立最終索引，請保留各階段產物')
    paths = selected_paths(settings, stages[0], request.get('ids'))
    request_settings(settings, request)
    if len(stages) > 1:
        if not settings.export_enabled:
            raise ValueError('連續執行需要保存中間產物，請先啟用階段輸出')
        from functions.markdown_processing.file_identity import source_identity
        identities = [source_identity(p) for p in paths]
        if None in identities or len(set(identities)) != len(identities):
            raise ValueError('連續執行的年度與股票代號缺失或重複，請分開處理')
    if 'chunk' in stages:
        request_settings(settings, {**request, 'stage': 'chunk'})
    if 'embed' in stages:
        if request.get('backend') not in ('bge', 'voyage'):
            raise ValueError('請選BGE或Voyage模型')
        if any(type(request.get(k, False)) is not bool for k in ('check_only', 'allow_voyage_api')):
            raise ValueError('建庫設定格式無效')
        if request['backend'] == 'voyage' and not request.get('allow_voyage_api'):
            raise ValueError('請先明確啟用Voyage API')
        from functions.embedding.index_target import validate_choice
        validate_choice(request.get('index_mode'), request.get('index_name'), request.get('collection'))
    return stages


def next_sources(settings, stage, output, original_paths):
    """只採本次剛完成批次的對應財報，不選其他歷史批次或Record。"""
    from functions.web_ui.catalog import STAGES, catalog, selected_paths
    from functions.markdown_processing.file_identity import source_identity, filename_identity
    from config.output_layout import BATCH_NAME_PATTERN
    if stage == 'embed':
        raise ValueError('建庫之後沒有下一階段')
    expected = {source_identity(p) for p in original_paths}
    root = getattr(settings, STAGES[stage][2]).resolve()
    batch = Path(output).resolve() if isinstance(output, str) and output else None
    if (batch is None or batch.parent != root or not batch.is_dir() or Path(output).is_symlink()
            or not re.fullmatch(BATCH_NAME_PATTERN, batch.name)):
        raise ValueError('本階段沒有可靠的本次輸出批次，停止銜接')
    following = ORDER[ORDER.index(stage) + 1]
    candidates = [r['id'] for r in catalog(settings, following)
                  if r['id'].split('/')[0] == batch.name
                  and filename_identity(Path(r['id']).name) in expected]
    identities = Counter(filename_identity(Path(p).name) for p in candidates)
    if set(identities) != expected or any(n != 1 for n in identities.values()):
        raise ValueError('本次輸出文件缺少或重複，停止銜接下一階段')
    selected_paths(settings, following, candidates)
    return candidates


def embedding_request(settings, request, ids):
    from functions.embedding.job_control import create_control
    # 切塊標籤模式屬於第四階段；第五階段必須沿用剛生成的chunk設定。
    keys = ('backend', 'embedding_profile', 'allow_voyage_api', 'check_only',
            'index_mode', 'index_name', 'collection', 'ocr')
    result = {k: request[k] for k in keys if k in request}
    result.update(stage='embed', ids=ids, vector_job_id=uuid.uuid4().hex)
    create_control(settings, result['vector_job_id'], ids)
    return result


def capture_intermediate(settings, stage, output, previous_batches):
    """Capture exact newly generated files; keep Record and refuse symlinks."""
    from functions.web_ui.catalog import STAGES
    from config.output_layout import BATCH_NAME_PATTERN
    root = getattr(settings, STAGES[stage][2]).resolve()
    batch = Path(output).resolve() if isinstance(output, str) and output else None
    project = settings.project_root.resolve()
    if (batch is None or not root.is_relative_to(project) or batch.parent != root
            or not batch.is_dir() or Path(output).is_symlink()
            or batch in previous_batches or not re.fullmatch(BATCH_NAME_PATTERN, batch.name)):
        raise ValueError('無法確認中間產物為本次新建批次，未安排清理')
    for parent in [root, *root.parents]:
        if parent == project.parent:
            break
        if parent.is_symlink():
            raise ValueError('中間產物路徑包含連結，未安排清理')
    files = []
    for file in batch.rglob('*'):
        if file.is_symlink():
            raise ValueError('中間產物包含連結，未安排清理')
        if file.is_file() and 'Record' not in file.relative_to(batch).parts:
            files.append((file, hashlib.sha256(file.read_bytes()).hexdigest()))
    return batch, files


def cleanup_intermediate(plans):
    # Validate all paths and hashes first. Delete individual owned files only;
    # never recursively delete a batch, project or source directory.
    for batch, files in plans:
        for file, digest in files:
            if (file.is_symlink() or not file.resolve().is_relative_to(batch)
                    or any(p.is_symlink() for p in file.parents if p.is_relative_to(batch))
                    or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest):
                raise ValueError('中間產物已變動，保留檔案供核對，未清理')
    removed = 0
    for batch, files in plans:
        for file, _ in files:
            file.unlink()
            removed += 1
        for directory in sorted((p for p in batch.rglob('*') if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
            if directory.is_symlink() or not directory.resolve().is_relative_to(batch):
                continue
            try:
                directory.rmdir()
            except OSError:
                pass  # Records and other files are preserved.
    return removed


def run_pipeline(app, request):
    from functions.web_ui.catalog import selected_paths
    stages = requested_stages(request)
    ids = list(request['ids'])
    original_paths = selected_paths(app.settings, stages[0], ids)
    final_only = request.get('final_output_only', False)
    cleanup_plans = []
    from functions.web_ui.catalog import STAGES
    previous_batches = set()
    for phase_stage in stages[:-1]:
        output_root = getattr(app.settings, STAGES[phase_stage][2])
        if output_root.is_dir():
            previous_batches.update(p.resolve() for p in output_root.iterdir())
    started = time.perf_counter()
    with app.lock:
        app.state.update(final_output_only=final_only, pipeline_start=stages[0], pipeline_end=stages[-1],
                         pipeline_phases=[{'stage':s, 'state':'pending'} for s in stages])
    try:
        for position, stage in enumerate(stages):
            with app.lock:
                if app.cancel_requested:
                    app.state.update(state='cancelled', current='連續流程已取消，後續階段未執行')
                    return
                phase = app.state['pipeline_phases'][position]
                phase.update(state='running')
                current = {**request, 'stage':stage, 'ids':ids}
                if stage == 'embed':
                    current = embedding_request(app.settings, request, ids)
                app.state.update(state='running', stage=stage, completed=0, total=len(ids),
                                 current='準備本階段工作環境', pipeline_position=position + 1)
                for key in ('output', 'error', 'page_progress', 'vector_job_id', 'embedding_files',
                            'stop_requested', 'stop_after', 'index_groups', 'group_number', 'group_total',
                            'index_group_name', 'skipped'):
                    app.state.pop(key, None)
                if stage == 'embed':
                    app.state.update(vector_job_id=current['vector_job_id'], embedding_files=ids,
                                     stop_requested=False)
            phase_started = time.perf_counter()
            app.run_single(current)
            with app.lock:
                phase.update(state=app.state['state'], elapsed_seconds=round(time.perf_counter() - phase_started, 6),
                             completed=app.state.get('completed',0), total=len(ids))
                if app.state.get('output'):
                    phase['output'] = app.state['output']
                if app.state['state'] != 'completed' or app.cancel_requested:
                    app.state['pipeline_message'] = '本階段未完整完成，後續階段未執行；已完成輸出保留。'
                    if app.cancel_requested and app.state['state'] == 'completed':
                        app.state.update(state='cancelled', current='連續流程已取消，後續階段未執行')
                    return
                if position + 1 < len(stages):
                    ids = next_sources(app.settings, stage, app.state.get('output'), original_paths)
                    if final_only:
                        cleanup_plans.append(capture_intermediate(app.settings, stage, app.state.get('output'), previous_batches))
        cleanup_message = '連續流程完成；各階段產物保存在原有輸出位置。'
        if final_only:
            try:
                removed = cleanup_intermediate(cleanup_plans)
                for phase in app.state['pipeline_phases'][:-1]:
                    phase['artifacts_retained'] = False
                app.state['intermediate_files_removed'] = removed
                cleanup_message = f'連續流程完成；只保留最終階段產物，中間產物已清理 {removed} 個檔案，Record 執行紀錄保留。'
            except (ValueError, OSError) as error:
                app.state['cleanup_warning'] = str(error)
                cleanup_message = '最終階段完成，但中間產物清理未完整完成；請核對保留檔案。'
        with app.lock:
            app.state.update(state='completed', current='所選階段全部完成',
                             pipeline_message=cleanup_message)
    except Exception as error:
        with app.lock:
            if app.cancel_requested:
                app.state.update(state='cancelled', current='連續流程已取消')
            else:
                phase = next((p for p in app.state['pipeline_phases'] if p['state']=='running'),None)
                if phase is not None:
                    phase['state']='failed'
                app.state.update(state='failed', error=str(error) if type(error) is ValueError else
                                 f'{type(error).__name__}：連續流程未完成，已停止後續階段')
    finally:
        with app.lock:
            app.state['pipeline_elapsed_seconds'] = round(time.perf_counter() - started, 6)
