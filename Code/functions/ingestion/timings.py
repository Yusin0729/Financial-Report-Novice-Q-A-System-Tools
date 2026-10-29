"""單份PDF階段計時；只保存秒數與次數，不保存財報文字。"""
import time
from contextlib import contextmanager

LABELS = {'model_load': '模型載入', 'layout': '版面分析', 'ocr': 'OCR',
          'table_structure': '表格辨識', 'markdown_output': 'Markdown 輸出'}


@contextmanager
def wall_timer(runtime, key):
    started = time.perf_counter()
    completed = False
    try:
        yield
        completed = True
    finally:
        item = runtime.setdefault('timing_details', {}).setdefault(key, {'seconds': 0.0, 'calls': 0, 'failed_calls': 0})
        item['seconds'] += time.perf_counter() - started
        item['calls'] += 1
        item['failed_calls'] += not completed


def capture_docling_timings(runtime, result):
    profiles = runtime.setdefault('docling_timings', {})
    for key, value in getattr(result, 'timings', {}).items():
        times = list(value.times)
        if times:
            item = profiles.setdefault(key, {'seconds': 0.0, 'calls': 0})
            item['seconds'] += sum(times)
            item['calls'] += len(times)


def finalize_timings(runtime):
    details, profiles = runtime.get('timing_details', {}), runtime.get('docling_timings', {})
    ocr = [d['timing'] for d in runtime.get('ocr_diagnostics', []) if isinstance(d.get('timing'), dict)]
    partial = runtime.get('status') != 'converted_needs_review'
    stages = {}

    def metric(key, entries, disabled=False):
        values = [v for v in entries if v is not None]
        stages[key] = {'label': LABELS[key], 'seconds': round(sum(v['seconds'] for v in values), 6) if values else None,
                       'calls': sum(v.get('calls', 1) for v in values),
                       'status': 'disabled' if disabled else ('partial' if partial else 'measured') if values else 'not_measured'}

    metric('model_load', [details.get('converter_setup'), details.get('pipeline_model_load')] +
           [{'seconds': d['model_load_seconds'], 'calls': d['model_load_calls']} for d in ocr if d['model_load_calls']])
    metric('layout', [profiles.get('layout'), profiles.get('layout_postprocess')])
    metric('table_structure', [profiles.get('table_structure')])
    metric('ocr', [{'seconds': d['ocr_seconds']} for d in ocr],
           disabled=runtime.get('settings', {}).get('ocr_enabled') is False)
    metric('markdown_output', [details.get('markdown_output')])
    runtime['stage_timings'] = {'schema_version': 'pdf-stage-timings/1.0', 'stages': stages,
                               'measurement': 'accumulated_stage_wall_seconds', 'additive': False,
                               'note': '階段可能重疊，不能直接加總為整份耗時；包含目錄與選頁備援，未取得不是0。'}
    return runtime['stage_timings']


def timing_text(summary):
    parts = []
    for key, label in LABELS.items():
        item = summary.get('stages', {}).get(key, {})
        value = item.get('seconds')
        text = '未啟用' if item.get('status') == 'disabled' else '未取得' if value is None else f'{value:.2f} 秒'
        if item.get('status') == 'partial':
            text += '（部分）'
        parts.append(f'{label}：{text}')
    return '；'.join(parts)
