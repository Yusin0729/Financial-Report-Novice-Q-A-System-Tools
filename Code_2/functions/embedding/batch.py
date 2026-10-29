"""批次讀取既有 chunk JSON；Record 僅供人工追溯。"""
import hashlib
import json
import re
import time
from pathlib import Path
from Code_2.config.embedding import BATCH_PATTERN, PREPARED_SCHEMA, PREPARE_RULE
from Code.functions.chunking.filenames import CHUNK_GLOB, parse_chunk_filename, validate_chunk_filename, chunk_record_prefix
from Code_2.functions.embedding.prepare import prepare_document
from Code_2.functions.experiments.export_output import output_paths, check_paths, export_prepared
from Code_2.functions.embedding.paths import batch_location, source_files, locations, outer_batch


def list_batches(settings):
    root = settings.input_dir
    return locations(root)


def prepare_batch(path, settings):
    batch = Path(path).resolve()
    batch_location(batch, settings.input_dir)
    sources = source_files(batch, CHUNK_GLOB)
    if not sources:
        raise ValueError('批次沒有chunk JSON')
    plans = []
    for source in sources:
        match = parse_chunk_filename(source.name)
        if not match:
            raise ValueError(f'chunk檔名格式無效：{source.name}')
        if source.resolve().parent != source.parent.resolve():
            raise ValueError('來源連結超出所選批次')
        prefix = chunk_record_prefix(match)
        paths = output_paths(settings, source.parent.relative_to(settings.input_dir.resolve()), prefix)
        if any(not p.resolve().is_relative_to(settings.output_dir.resolve()) for p in paths.values()):
            raise ValueError('輸出連結超出指定目錄')
        if settings.export_enabled:
            check_paths(paths)  # 整批預檢，避免處理到一半才發現既有產物。
        plans.append((source, prefix, paths))
    records = []
    for source, prefix, paths in plans:
        started = time.perf_counter()
        result = None
        record = {'schema_version': 'embedding-prepare-run/1.0', 'prepared_schema_version': PREPARED_SCHEMA,
                  'rule_version': PREPARE_RULE, 'batch': outer_batch(source), 'source': str(source),
                  'status': 'failed', 'export_enabled': settings.export_enabled,
                  'model': None, 'token_check_status': 'pending_model_selection'}
        try:
            raw = source.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            origin_path = source.parent / 'Record' / f'{prefix}_reocrd'
            doc = json.loads(raw.decode('utf-8'))
            _, mode, _ = batch_location(source.parent, settings.input_dir)
            if mode and doc.get('chunking', {}).get('mode') != mode:
                raise ValueError('模式資料夾與chunk設定不符，未猜測或更名')
            origin = None
            origin_issue = None
            if origin_path.is_file():
                try:
                    origin = json.loads(origin_path.read_text(encoding='utf-8'))
                    output = origin.get('outputs') if isinstance(origin, dict) else None
                    info = output.get('json') if isinstance(output, dict) else None
                    if (not isinstance(origin, dict) or origin.get('batch') != outer_batch(source) or
                            origin.get('doc_id') != doc.get('doc_id') or
                            not isinstance(info, dict) or info.get('sha256') != digest):
                        origin_issue = 'chunk Record 的批次、文件或雜湊與 JSON 不符'
                        origin = None
                except (OSError, ValueError, UnicodeError) as error:
                    origin_issue = f'chunk Record 無法讀取：{type(error).__name__}'
                    origin = None
            else:
                origin_issue = 'chunk Record 不存在'
            result = prepare_document(doc, input_sha256=digest)
            first = result['chunks'][0]['metadata']
            validate_chunk_filename(source.name, doc, first['stock_code'])
            if source.read_bytes() != raw:
                raise ValueError('chunk在處理期間變更')
            record.update(status='prepared_needs_review', doc_id=doc['doc_id'], input_sha256=digest,
                          origin_record=str(origin_path) if origin_path.is_file() else None,
                          source_record_issue=origin_issue,
                          temporary_fallback=origin.get('temporary_fallback') if origin else None,
                          chunk_count=len(result['chunks']),
                          table_chunk_count=sum(c['metadata']['content_type'] == 'table' for c in result['chunks']),
                          html_table_count=sum(c['preparation']['html_table_count'] for c in result['chunks']))
        except KeyboardInterrupt:
            result = None
            record.update(status='interrupted', error='使用者中止，未輸出部分前處理結果')
        except Exception as error:
            result = None
            record.update(status='failed', error=f'{type(error).__name__}: {error}')
        record['elapsed_seconds'] = round(time.perf_counter() - started, 6)
        # EXPERIMENT_ONLY：移除寫檔不影響prepare_document的記憶體結果。
        target = export_prepared(settings, paths, record, result)
        if record['status'] != 'prepared_needs_review':
            result = None
        print(f'{source.name}：{record["status"]}；' +
              (f'{record["chunk_count"]}個chunk，tokens待檢查' if result else record.get('error', '未完成')))
        records.append({**record, 'result': result, 'output_dir': str(target) if target else None})
        if record['status'] == 'interrupted':
            break
    return records
