"""獨立驗證 prepared JSON；同批 Record 是可選的追溯報告。"""
import hashlib
import json
import re
from pathlib import Path
from Code.config.embedding import BATCH_PATTERN, PREPARED_SCHEMA
from Code.functions.embedding.metadata import build_metadata
from Code.functions.embedding.prepare import validate_document
from Code.functions.embedding.paths import batch_location, source_files, outer_batch


def validate_prepared(doc):
    if not isinstance(doc, dict) or doc.get('schema_version') != PREPARED_SCHEMA or not doc.get('chunks'):
        raise ValueError('需要financial-embedding-prepared/2.0；舊檔請由chunk重新前處理，不直接改版本號')
    originals = [c['original_chunk'] for c in doc['chunks']]
    modes = doc.get('embedding_context_modes')
    if 'embedding_context_modes' in doc:
        from Code.functions.embedding.context_modes import validate_modes
        modes = validate_modes(modes)
    year, stock = validate_document({'schema_version': doc['source_chunk_schema'], 'doc_id': doc['doc_id'],
                                     'source_sha256': doc['source_sha256'], 'rule_version':doc.get('source_rule_version'), 'chunks': originals,
                                     'parents': doc.get('parents', []), 'chunking': doc.get('chunking'),
                                     **({'embedding_context_modes':modes} if any('embedding_context_mode' in c for c in originals) else {})})
    for item in doc['chunks']:
        if modes is not None:
            from Code.functions.embedding.context_modes import embedding_text
            chunk = item['original_chunk']
            if item['embedding_text'] != embedding_text(chunk, modes[chunk['content_type']]):
                raise ValueError('embedding文字與所選脈絡模式不符')
        if (item['chunk_id'] != item['original_chunk']['chunk_id'] or
                not isinstance(item['embedding_text'], str) or not item['embedding_text'].strip() or
                item['metadata'] != build_metadata(item['original_chunk'], stock_code=stock, report_year=year)):
            raise ValueError('prepared內容／metadata與原chunk不符')
    return year, stock


def prepared_sources(path, settings):
    batch = Path(path).resolve()
    batch_location(batch, settings.output_dir)
    sources = source_files(batch, '*_prepared.json')
    if not sources:
        raise ValueError('批次沒有*_prepared.json')
    return sources


def load_prepared(source):
    source = Path(source).resolve()
    match = re.fullmatch(r'(\d{4})_(\d+)(?:_([1-9]\d*))?_prepared\.json', source.name)
    if not match:
        raise ValueError('prepared檔名無效')
    prefix = '_'.join(value for value in match.groups() if value is not None)
    origin_path = source.parent / 'Record' / f'{prefix}_reocrd'
    raw = source.read_bytes()
    doc = json.loads(raw.decode('utf-8'))
    if source.parent.name in ('original','parent_child') and doc.get('chunking', {}).get('mode') != source.parent.name:
        raise ValueError('模式資料夾與prepared設定不符')
    digest = hashlib.sha256(raw).hexdigest()
    year, stock = validate_prepared(doc)
    if match.group(1, 2) != (str(year), str(stock)):
        raise ValueError('prepared檔名與文件身分不符')
    if match[3] is not None:
        spec = doc.get('chunking', {})
        if spec.get('mode') != 'parent_child' or int(match[3]) != spec.get('recursive_threshold'):
            raise ValueError('prepared檔名字數與切分設定不符')
    record = {}
    if origin_path.is_file():
        try:
            record = json.loads(origin_path.read_text(encoding='utf-8'))
            outputs = record.get('outputs') if isinstance(record, dict) else None
            info = outputs.get('json') if isinstance(outputs, dict) else None
            if (not isinstance(record, dict) or record.get('batch') != outer_batch(source) or
                    record.get('doc_id') != doc.get('doc_id') or
                    not isinstance(info, dict) or info.get('sha256') != digest):
                record = record if isinstance(record, dict) else {}
                record['source_record_issue'] = 'prepared Record 的批次、文件或雜湊與 JSON 不符'
        except (OSError, ValueError, UnicodeError) as error:
            record = {'source_record_issue': f'prepared Record 無法讀取：{type(error).__name__}'}
    else:
        record = {'source_record_issue': 'prepared Record 不存在'}
    if source.read_bytes() != raw:
        raise ValueError('prepared在載入期間變更')
    return doc, digest, record
