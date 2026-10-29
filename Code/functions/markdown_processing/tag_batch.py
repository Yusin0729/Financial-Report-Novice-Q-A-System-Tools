"""processed批次標題分類；只使用正文，不讀目錄JSON、不呼叫Gemini。"""
import hashlib
import json
import re
import time
from pathlib import Path
from dataclasses import asdict
from config.output_layout import BATCH_NAME_PATTERN

from schemas import TaggingMetadata
from functions.markdown_processing.comment_tagging import tag_comments
from functions.markdown_processing.file_identity import filename_identity
from functions.markdown_processing.load_source import load_source
from functions.markdown_processing.batch_selection import batch_sources


def list_processed_batches(settings):
    root = settings.markdown_processed_output_dir
    return sorted(p for p in root.iterdir() if p.is_dir() and
                  re.fullmatch(BATCH_NAME_PATTERN, p.name)) if root.is_dir() else []


def tag_processed_batch(path: Path, settings, *, source_files=None, output_batch=None):
    batch = path.resolve()
    if batch.parent != settings.markdown_processed_output_dir.resolve() or not batch.is_dir() or not re.fullmatch(
            BATCH_NAME_PATTERN, batch.name):
        raise ValueError('請選擇 markdown_processed 下的 Financial 批次')
    sources = batch_sources(batch, '*_processed.md', source_files)
    from functions.experiments.export_output import stage_output_batch
    target_batch = stage_output_batch(settings, 'tagged', output_batch)
    # EXPERIMENT_ONLY：預先檢查同批輸出，避免覆寫。
    from functions.experiments.export_output import comment_tag_paths, check_markdown_paths, export_comment_tags
    plans = []
    for source in sources:
        identity = filename_identity(source.name)
        if not identity:
            raise ValueError(f'無法取得檔名年份與股票代號：{source.name}')
        prefix = '_'.join(identity)
        paths = comment_tag_paths(settings, target_batch.name, prefix)
        if settings.export_enabled:
            check_markdown_paths(paths)
        plans.append((source, identity, prefix, paths))
    records = []
    for source, identity, prefix, paths in plans:
        started = time.perf_counter()
        result = None
        record = {'schema_version': 'comment-tag-run/1.0', 'batch': target_batch.name,
                  'source_batch': batch.name,
                  'source': str(source), 'status': 'needs_confirmation',
                  'page_policy': 'preserve_original_pdf_page_markers',
                  'heading_policy': 'classify_processed_headings_without_main_title',
                  'full_document_preserved': True}
        record['runtime_config'] = {'cpu_threads': None, 'batch_size': None, 'batch_unit': None}
        try:
            _, text, before = load_source(source)
            origin_path = batch / 'Record' / f'{prefix}_reocrd'
            origin = None
            origin_issue = None
            if origin_path.is_file():
                try:
                    origin = json.loads(origin_path.read_text(encoding='utf-8'))
                    if (not isinstance(origin, dict) or origin.get('batch') != batch.name
                            or origin.get('output_sha256') != before):
                        origin_issue = 'processed Record 的批次或雜湊與正文不符'
                        origin = None
                except (OSError, ValueError, UnicodeError) as error:
                    origin_issue = f'processed Record 無法讀取：{type(error).__name__}'
            else:
                origin_issue = 'processed Record 不存在'
            record.update(origin_record=str(origin_path) if origin_path.is_file() else None,
                          source_record_issue=origin_issue)
            record.update(main_title_source='disabled', temporary_fallback=False)
            metadata = TaggingMetadata(report_year=identity[0], stock_code=identity[1])
            result = tag_comments(text, None, metadata)
            if hashlib.sha256(source.read_bytes()).hexdigest() != before:
                result = None
                raise ValueError('來源 Markdown 處理期間變更')
            record.update(status='tagged_needs_review',
                          version=result.version, source_sha256=before,
                          output_sha256=hashlib.sha256(result.markdown.encode('utf-8')).hexdigest(),
                          metadata=asdict(metadata), removed_page_lines=list(result.removed_page_lines),
                          block_counts=result.block_counts, boundary_added_newlines=result.boundary_added_newlines,
                          table_continuation_joins=list(result.table_continuation_joins),
                          issues=list(result.issues))
            label = '正文標籤完成'
            print(f'{source.name}：{label}；保留來源內容，不在此階段清除頁碼。')
        except KeyboardInterrupt:
            result = None
            record.update(status='interrupted', error='使用者中止加標籤')
        except Exception as error:
            result = None
            record['error'] = f'{type(error).__name__}: {error}'
            print(f'{source.name}：加標籤待確認：{record["error"]}')
        record['elapsed_seconds'] = round(time.perf_counter() - started, 6)
        # EXPERIMENT_ONLY：核心結果獨立回傳；可停用實驗寫檔。
        target = export_comment_tags(settings, paths, record, result)
        records.append({**record, 'result': result, 'output_dir': str(target) if target else None})
        if record['status'] == 'interrupted':
            break
    return records
