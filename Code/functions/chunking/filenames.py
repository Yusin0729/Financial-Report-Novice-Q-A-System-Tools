"""chunk檔名契約：父子切法附字數門檻，舊檔仍可讀取。"""
import re
from pathlib import Path

CHUNK_GLOB = '*_chunk*.json'
CHUNK_NAME = re.compile(r'(?P<year>\d{4})_(?P<stock>\d+)_chunk(?:_(?P<limit>[1-9]\d*))?(?:_text-(?P<text_mode>body|description|full)_table-(?P<table_mode>body|description|full))?\.json')


def parse_chunk_filename(name):
    return CHUNK_NAME.fullmatch(Path(name).name)


def validate_chunk_filename(name, doc, stock):
    match = parse_chunk_filename(name)
    if not match or (match['year'], match['stock']) != (doc['doc_id'][:4], str(stock)):
        raise ValueError('來源檔名與doc_id不符')
    if match['limit'] is not None:
        spec = doc.get('chunking', {})
        if spec.get('mode') != 'parent_child' or int(match['limit']) != spec.get('recursive_threshold'):
            raise ValueError('檔名字數後綴與parent_child切分設定不符')
    modes = doc.get('embedding_context_modes', {})
    if (match['text_mode'],match['table_mode']) != (modes.get('text'),modes.get('table')):
        raise ValueError('檔名脈絡模式與chunk設定不符')
    return match


def chunk_record_prefix(match):
    prefix = f"{match['year']}_{match['stock']}"
    prefix += (f"_{match['limit']}" if match['limit'] is not None else '')
    if match['text_mode']:
        prefix += f"_text-{match['text_mode']}_table-{match['table_mode']}"
    return prefix
