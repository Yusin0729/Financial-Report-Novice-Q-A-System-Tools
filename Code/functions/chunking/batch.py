"""tagged→chunk批次入口；來源驗證與實驗寫檔分離，不使用外部服務。"""
import hashlib
import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from config.chunking import CHUNK_RULE_VERSION, CHUNK_SCHEMA_VERSION, CHUNK_MARKDOWN_VERSION, MIN_TAGGING_VERSION
from config.chunking import SEMANTIC_SCHEMA_VERSION, SEMANTIC_RULE_VERSION, SEMANTIC_MARKDOWN_VERSION
from config.output_layout import BATCH_NAME_PATTERN
from functions.chunking.chunks import chunk_tagged
from functions.chunking.parent_child import SCHEMA as CONTEXT_SCHEMA, RULE as CONTEXT_RULE
from functions.markdown_processing.file_identity import filename_identity
from functions.markdown_processing.load_source import load_source
from functions.markdown_processing.batch_selection import batch_sources


_TAGGING_VERSION = re.compile(r'<!-- TAGGING_VERSION: markdown-comment-tagging/(\d+)\.(\d+) -->')
_EMPTY_HD = re.compile(r'^<hd\d+>\s*</hd\d+>$', re.M)
_HD2 = re.compile(r'^<hd2>(.*?)</hd2>$')


def tagged_compatibility(text):
    """新版由正文版本決定；舊版無版本時僅從實際標籤推斷相容規則。"""
    first_line = text.splitlines()[0].lstrip('\ufeff') if text else ''
    match = _TAGGING_VERSION.fullmatch(first_line)
    if match:
        version = tuple(map(int, match.groups()))
        if version < MIN_TAGGING_VERSION:
            raise ValueError('來源tagged版本早於目前支援範圍')
        return version < (2, 6), version < (2, 5), 'markdown_header'
    empty_hd = bool(_EMPTY_HD.search(text))
    previous_heading = None
    page_header = False
    repeated_snapshot = False
    for line in text.splitlines():
        if line.startswith('<!-- Page: '):
            page_header = True
        elif line.startswith('<!-- MAIN_TITLE: '):
            continue
        elif (heading := _HD2.fullmatch(line)):
            title = heading[1].strip()
            if page_header and title and title == previous_heading:
                repeated_snapshot = True
            if title:
                previous_heading = title
            page_header = False
        elif line.strip() and not line.startswith('<!--'):
            page_header = False
    return empty_hd or repeated_snapshot, empty_hd, 'content_inference_unversioned'


def list_tagged_batches(settings):
    root = settings.markdown_tagged_output_dir
    return sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(BATCH_NAME_PATTERN, p.name)) if root.is_dir() else []


def chunk_tagged_batch(path: Path, settings, *, source_files=None, output_batch=None):
    batch = path.resolve()
    if batch.parent != settings.markdown_tagged_output_dir.resolve() or not batch.is_dir() or not re.fullmatch(BATCH_NAME_PATTERN, batch.name):
        raise ValueError('請選擇markdown_tagged下的Financial批次')
    sources = batch_sources(batch, '*_tagged.md', source_files)
    from functions.experiments.export_output import stage_output_batch
    target_batch = stage_output_batch(settings, 'chunk', output_batch)
    # EXPERIMENT_ONLY：整批預先檢查，不覆寫JSON／Markdown／Record。
    from functions.experiments.export_output import chunk_run_paths, check_markdown_paths, export_chunks
    plans = []
    for source in sources:
        identity = filename_identity(source.name)
        if identity is None:
            raise ValueError(f'無法取得年份與股票代號：{source.name}')
        paths = chunk_run_paths(settings, target_batch.name, '_'.join(identity))
        if settings.export_enabled:
            check_markdown_paths(paths)
        plans.append((source, identity, paths))
    records = []
    for source, identity, paths in plans:
        started = time.perf_counter()
        result = None
        record = {'schema_version': 'chunk-run/1.0',
                  'chunk_schema_version': CONTEXT_SCHEMA if settings.chunking.mode == 'parent_child' else SEMANTIC_SCHEMA_VERSION,
                  'rule_version': CONTEXT_RULE if settings.chunking.mode == 'parent_child' else SEMANTIC_RULE_VERSION,
                  'batch': target_batch.name, 'source': str(source),
                  'source_batch': batch.name,
                  'markdown_format_version': 'chunk-markdown/5.0' if settings.chunking.mode == 'parent_child' else SEMANTIC_MARKDOWN_VERSION,
                  'status': 'needs_confirmation', 'config': asdict(settings.chunking)}
        record['runtime_config'] = {'cpu_threads': None, 'batch_size': None, 'batch_unit': None}
        try:
            _, text, before = load_source(source)
            origin_path = batch / 'Record' / f'{"_".join(identity)}_reocrd'
            origin = None
            origin_issue = None
            if origin_path.is_file():
                try:
                    origin = json.loads(origin_path.read_text(encoding='utf-8'))
                    if (not isinstance(origin, dict) or origin.get('batch') != batch.name
                            or origin.get('output_sha256') != before):
                        origin_issue = 'tagged Record 的批次或雜湊與正文不符'
                        origin = None
                except (OSError, ValueError, UnicodeError) as error:
                    origin_issue = f'tagged Record 無法讀取：{type(error).__name__}'
                    origin = None
            else:
                origin_issue = 'tagged Record 不存在'
            snapshots, empty_hd, format_source = tagged_compatibility(text)
            record.update(source_sha256=before,
                          origin_record=str(origin_path) if origin_path.is_file() else None,
                          source_record_issue=origin_issue,
                          temporary_fallback=origin.get('temporary_fallback') if origin else None,
                          tagging_format_source=format_source,
                          legacy_page_snapshots=snapshots, legacy_empty_hd=empty_hd)
            result = chunk_tagged(text, identity=identity, source_sha256=before, config=settings.chunking,
                                  legacy_page_snapshots=record['legacy_page_snapshots'],
                                  legacy_empty_hd=record['legacy_empty_hd'])
            if hashlib.sha256(source.read_bytes()).hexdigest() != before:
                result = None
                raise ValueError('tagged在處理期間變更')
            from collections import Counter
            record.update(status='chunked_needs_review', doc_id=result.document['doc_id'],
                          excluded_prefix_end=result.excluded_prefix_end,
                          chunk_count=len(result.document['chunks']),
                          parent_count=len(result.document['parents']),
                          issues=result.document['issues'],
                          counts_by_type=dict(Counter(c['content_type'] for c in result.document['chunks'])),
                          cut_reasons=dict(Counter(c['cut_reason'] for c in result.document['chunks'])))
            print(f'{source.name}：完成{record["chunk_count"]}個chunk，保留來源正文；待人工核對。')
            for issue in record['issues']:
                location = issue.get('parent_id') or f'來源位置{issue.get("source_start", "未知")}'
                print(f'待核對：{location}／{issue["status"]}；保留原始來源與完整內容。')
        except KeyboardInterrupt:
            result = None
            record.update(status='interrupted', error='使用者中止chunk，未輸出部分結果')
        except Exception as error:
            result = None
            record['error'] = f'{type(error).__name__}: {error}'
            print(f'{source.name}：chunk待確認：{record["error"]}')
        record['elapsed_seconds'] = round(time.perf_counter() - started, 6)
        # EXPERIMENT_ONLY：核心回傳記憶體結果，--no-export不依賴Output。
        target = export_chunks(settings, paths, record, result)
        if record['status'] in ('failed', 'interrupted') and result is not None:
            print(f'{source.name}：未完成輸出，{record.get("error", "請檢查Record")}')
        records.append({**record, 'result': result, 'output_dir': str(target) if target else None})
        if record['status'] == 'interrupted':
            break
    return records
