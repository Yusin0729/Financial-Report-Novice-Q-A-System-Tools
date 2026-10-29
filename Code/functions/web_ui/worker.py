"""獨立工作程序：只呼叫既有四階段入口；stdout 為簡短 JSON 事件。"""
import contextlib
import json
import math
import time
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)

def execute(request, settings, emit_event=emit, before_item=None):
    from functions.web_ui.catalog import selected_paths, STAGES
    stage = request['stage']
    paths = selected_paths(settings, stage, request['ids'])
    from functions.web_ui.request_settings import request_settings
    settings = request_settings(settings, request)
    from main import run_markdown, process_raw_batch, tag_processed_batch, chunk_tagged_batch
    batch = None
    if stage != 'raw':
        from functions.markdown_processing.file_identity import filename_identity
        identities = [filename_identity(path.name) for path in paths]
        if None in identities or len(set(identities)) != len(identities):
            raise ValueError('所選來源的年度與股票代號缺失或重複，無法放入同一批次；請分開處理')
        if settings.export_enabled:
            # EXPERIMENT_ONLY：同次點擊共用一個新批次，包含來自不同來源資料夾的文件。
            from functions.experiments.export_output import stage_output_batch
            batch = stage_output_batch(settings, stage)
            emit_event({'output': str(batch)})
    if stage == 'raw' and settings.export_enabled:
        # EXPERIMENT_ONLY：沿用既有集中輸出，不另外創造產物格式。
        from functions.experiments.export_output import create_markdown_batch
        batch = create_markdown_batch(settings.markdown_output_dir)
        emit_event({'output': str(batch)})
    failed = False
    for index, path in enumerate(paths):
        emit_event({'current': path.name, 'completed': index, 'total': len(paths)})
        runtime_config = ({'cpu_threads': settings.pdf_cpu_threads if settings.pdf_parser == 'docling' else None,
                           'pdf_parser': settings.pdf_parser,
                           'fallback_cpu_threads':settings.pdf_cpu_threads if settings.pdf_parser == 'inspector' else None,
                           'batch_size': settings.pdf_batch_size, 'batch_unit': 'pipeline'}
                          if stage == 'raw' else
                          {'cpu_threads': None, 'batch_size': None, 'batch_unit': None})
        started = time.perf_counter()
        try:
            if before_item is not None:
                before_item(index)
            started = time.perf_counter()
            if stage == 'raw':
                records = [run_markdown(
                    path, settings, batch_dir=batch,
                    progress_callback=lambda event, file_index=index, file_name=path.name:
                        emit_event({'page_progress': {**event, 'file_index': file_index,
                            'file_name': file_name, 'file_total': len(paths)}}),
                )]
            else:
                function = {'processed': process_raw_batch, 'tagged': tag_processed_batch,
                            'chunk': chunk_tagged_batch}[stage]
                source_root = getattr(settings, STAGES[stage][1]).resolve()
                relative = path.relative_to(source_root)
                batch_path = source_root / relative.parts[0]
                records = function(batch_path, settings, source_files=[path.relative_to(batch_path).as_posix()],
                                   output_batch=batch)
            if not records:
                raise ValueError('沒有處理結果')
            for record in records:
                status = record.get('status', 'failed')
                success = status in {'converted_needs_review', 'processed_needs_review',
                    'tagged_needs_review', 'tagged_temporary_fallback_needs_review', 'chunked_needs_review'}
                failed |= not success
                source = record.get('source', path.name)
                if isinstance(source, dict):
                    source = source.get('filename') or source.get('path') or path.name
                result = {'name': Path(str(source)).name, 'status': status,
                    'message': '完成，請人工核對' if success else '未完整完成，請查看此批 Record 的失敗階段與原因'}
                if stage == 'raw':
                    result.update(_raw_metrics(record, success=success))
                elapsed = record.get('elapsed_seconds')
                if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
                    elapsed = round(time.perf_counter() - started, 6)
                result['elapsed_seconds'] = elapsed
                result['runtime_config'] = record.get('runtime_config', runtime_config)
                emit_event({'result': result})
        except Exception as error:
            failed = True
            message = ('輸出已存在，未覆寫；請查看輸出資料夾' if isinstance(error, FileExistsError)
                       else f'{type(error).__name__}：此項未完成，請查看既有批次紀錄與來源格式')
            failure = {'name': path.name, 'status': 'failed', 'message': message,
                'elapsed_seconds': round(time.perf_counter() - started, 6),
                'runtime_config': runtime_config}
            if stage == 'raw':
                failure.update(_raw_metrics({'elapsed_seconds': failure['elapsed_seconds'],
                    'settings': settings.pdf_manifest()}, success=False))
            emit_event({'result': failure})
        emit_event({'completed': index + 1})
    emit_event({'state': 'completed_with_errors' if failed else 'completed'})


def _raw_metrics(record, *, success):
    """每份 PDF 的整體處理速度摘要；OCR 區域數來自既有診斷資料。"""
    elapsed = record.get('elapsed_seconds')
    source = record.get('source') or {}
    selected = (record.get('selection') or {}).get('selected_pdf_pages')
    page_count = len(selected) if isinstance(selected, list) else None
    settings = record.get('settings') or {}
    ocr_enabled = settings.get('ocr_enabled')
    diagnostics = record.get('ocr_diagnostics')
    metrics = {'elapsed_seconds': elapsed, 'pdf_page_count': page_count,
               'stage_timings': record.get('stage_timings'),
               'ocr_enabled': ocr_enabled, 'ocr_region_count': None,
               'ocr_pages': None, 'pages_per_minute': None, 'ocr_regions_per_minute': None}
    if success and isinstance(elapsed, (int, float)) and elapsed > 0:
        if isinstance(page_count, int) and page_count >= 0:
            metrics['pages_per_minute'] = round(page_count * 60 / elapsed, 2)
        if ocr_enabled is False:
            metrics['ocr_region_count'] = 'disabled'
        elif isinstance(diagnostics, list):
            count = sum(len(item.get('regions', [])) for item in diagnostics if isinstance(item, dict))
            metrics['ocr_region_count'] = count
            metrics['ocr_regions_per_minute'] = round(count * 60 / elapsed, 2)
            metrics['ocr_pages'] = sorted({item['pdf_page'] for item in diagnostics
                if isinstance(item, dict) and item.get('regions')
                and isinstance(item.get('pdf_page'), int)})
        elif ocr_enabled is True:
            metrics['ocr_region_count'] = 'unavailable'
    elif ocr_enabled is False:
        metrics['ocr_region_count'] = 'disabled'
    elif ocr_enabled is True and not isinstance(diagnostics, list):
        metrics['ocr_region_count'] = 'unavailable'
    return metrics

if __name__ == '__main__':
    request = json.loads(sys.stdin.readline())
    from config.settings import SETTINGS
    output = sys.stdout
    def send(event):
        output.write(json.dumps(event, ensure_ascii=False) + '\n')
        output.flush()
    def response():
        line = sys.stdin.readline()
        if not line:
            raise KeyboardInterrupt('本機服務已中止工作')
        reply = json.loads(line)
        if not reply.get('ok'):
            raise ValueError(reply.get('error', '輸出授權失敗'))
        return reply
    def before_item(index):
        send({'item_started':index})
        response()
    def prepare_output(path):
        send({'artifact_requested':str(path.resolve())})
        return response()['identity']
    try:
        # 不把第三方套件全文、HTTP body 或金鑰輸出到瀏覽器／新日誌。
        with open(os.devnull, 'w', encoding='utf-8') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            from functions.experiments.output_ownership import output_observer
            # EXPERIMENT_ONLY：只追蹤實驗輸出擁有權，停用寫檔不影響核心轉換。
            with output_observer(prepare_output):
                execute(request, SETTINGS, send, before_item=before_item)
    except Exception as error:
        send({'state': 'failed', 'error': f'{type(error).__name__}：工作未完成，請核對環境與來源'})
        sys.exit(1)
