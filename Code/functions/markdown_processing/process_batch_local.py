"""本機第二階段：直接驗證 raw Markdown，再補標題、清除獨立頁碼。"""
import hashlib
import json
import re
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.output_layout import BATCH_NAME_PATTERN
from functions.markdown_processing.file_identity import filename_identity
from functions.markdown_processing.load_source import load_source, is_selectable_markdown
from functions.markdown_processing.page_cleanup import CLEANUP_VERSION
from functions.markdown_processing.batch_selection import batch_sources
from functions.markdown_processing.note_processing import process_note_content


def _retryable_failed_record(paths, source):
    """只允許封存同來源、未留下有效產物的失敗紀錄。"""
    report = paths['record']
    if not report.is_file() or paths['markdown'].exists() or paths['toc'].exists():
        return None
    previous = report.read_bytes()
    try:
        data = json.loads(previous.decode('utf-8'))
    except (ValueError, UnicodeError):
        return None
    if not isinstance(data, dict) or data.get('status') != 'failed' or data.get('source') != str(source):
        return None
    return previous


def list_raw_batches(settings):
    root = settings.markdown_output_dir
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and
                  re.fullmatch(BATCH_NAME_PATTERN, p.name))


def process_raw_batch(path: Path, settings, *, source_files=None, output_batch=None) -> list[dict]:
    batch = path.resolve()
    if batch.parent != settings.markdown_output_dir.resolve() or not re.fullmatch(
            BATCH_NAME_PATTERN, batch.name) or not batch.is_dir():
        raise ValueError('請選擇 markdown_raw 下的 Financial 批次資料夾')
    sources = batch_sources(batch, '*_raw.md', source_files)
    from functions.experiments.export_output import stage_output_batch
    target_batch = stage_output_batch(settings, 'processed', output_batch)
    from functions.experiments.export_output import processed_run_paths, check_markdown_paths, export_processed_run
    plans = []
    for source in sources:
        identity = filename_identity(source.name)
        if identity is None:
            raise ValueError(f'無法取得年度與代號：{source.name}')
        prefix = '_'.join(identity)
        paths = processed_run_paths(settings, target_batch.name, prefix)
        retry_record = _retryable_failed_record(paths, source) if settings.export_enabled else None
        if settings.export_enabled:
            check_markdown_paths({key: value for key, value in paths.items()
                                  if key != 'record' or retry_record is None})
        plans.append((source, prefix, paths, retry_record))
    results = []
    for source, prefix, paths, retry_record in plans:
        started = time.perf_counter()
        heading = None
        record = {'schema_version': 'markdown-processed-run/1.2', 'batch': target_batch.name,
                  'source_batch': batch.name,
                  'source': str(source), 'status': 'failed', 'stage': 'validate_raw',
                  'toc_status': 'not_generated', 'export_enabled': settings.export_enabled}
        record['runtime_config'] = {'cpu_threads': None, 'batch_size': None, 'batch_unit': None}
        try:
            if not is_selectable_markdown(source):
                raise ValueError('來源不是含可靠 PDF 頁序的 raw Markdown')
            _, text, before = load_source(source)
            from functions.markdown_processing.page_markers import parse_page_marker
            pages = [number for line in text.splitlines()
                     if (number := parse_page_marker(line)) is not None]
            if not pages or pages != sorted(set(pages)):
                raise ValueError('raw Markdown 缺少可靠且遞增的 PDF 實體頁序')
            identity = filename_identity(source.name)
            for line in text.splitlines():
                parse_page_marker(line, expected_identity=identity)
            # Record 僅供人工追溯：不存在、損壞或缺 selection 都不阻擋補標題。
            origin_path = batch / 'Record' / f'{prefix}_reocrd'
            selection = None
            origin_issue = None
            if origin_path.is_file():
                try:
                    origin = json.loads(origin_path.read_text(encoding='utf-8'))
                    if (isinstance(origin, dict) and origin.get('batch_dir') == str(batch)
                            and isinstance(origin.get('selection'), dict)):
                        selection = origin['selection']
                    else:
                        origin_issue = '來源 Record 沒有同批新版選頁資訊'
                except (OSError, ValueError, UnicodeError) as error:
                    origin_issue = f'來源 Record 無法讀取：{type(error).__name__}'
            else:
                origin_issue = '來源 Record 不存在'
            record.update(origin_record=str(origin_path) if origin_path.is_file() else None,
                          source_sha256=before, source_pdf_pages=pages,
                          selection_status='reported_new_selection' if selection else 'unverified_legacy_raw',
                          source_record_issue=origin_issue)
            if selection:
                record['selection_report'] = selection
            record['stage'] = 'headings_and_page_cleanup'
            heading, removed, scope = process_note_content(text)
            cleaned = heading.markdown
            record['processing_scope'] = scope
            if hashlib.sha256(source.read_bytes()).hexdigest() != before:
                heading = None
                raise ValueError('來源 Markdown 在處理期間改變')
            record.update(status='processed_needs_review', stage='complete',
                          rule_version=heading.rule_version, page_cleanup_version=CLEANUP_VERSION,
                          removed_page_lines=list(removed), changes=[asdict(c) for c in heading.changes],
                          output_sha256=hashlib.sha256(cleaned.encode('utf-8')).hexdigest())
        except KeyboardInterrupt:
            heading = None
            record.update(status='interrupted', error='使用者中止')
        except Exception as error:
            heading = None
            record['error'] = f'{type(error).__name__}: {error}'
        record['elapsed_seconds'] = round(time.perf_counter() - started, 6)
        record['markdown_files'] = {'processed': paths['markdown'].name} if heading else {}
        record['toc_file'] = None
        # EXPERIMENT_ONLY：集中寫出第二階段檢查產物。
        if retry_record is not None:
            if paths['record'].read_bytes() != retry_record or paths['markdown'].exists() or paths['toc'].exists():
                raise ValueError('失敗紀錄或輸出在執行期間改變；未覆寫')
            suffix = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
            archive = paths['record'].with_name(paths['record'].name + f'.failed-{suffix}')
            if archive.exists():
                raise FileExistsError(f'失敗紀錄封存名稱已存在：{archive}')
            from functions.experiments.output_ownership import exclusive_output
            with exclusive_output(archive, 'xb') as stream:
                stream.write(retry_record)
            if archive.read_bytes() != retry_record:
                raise OSError('失敗紀錄封存核對失敗；原紀錄未覆寫')
            paths['record'].unlink()
            record['previous_failed_record'] = str(archive)
        target = export_processed_run(settings, paths, record, heading, None)
        results.append({**record, 'result': heading, 'toc_result': None,
                        'output_dir': str(target) if target else None})
        if record['status'] == 'interrupted':
            break
    return results
