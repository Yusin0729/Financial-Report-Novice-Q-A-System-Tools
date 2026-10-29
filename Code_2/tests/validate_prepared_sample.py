"""唯讀核對真實既有產物；不重跑模型、前處理或寫檔。

在專案根目錄以 python Code_2/tests/validate_prepared_sample.py chunk.json prepared.json 執行。
數字出現次數檢查只能發現遺失，不能證明欄位對應／OCR本來就正確。
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.tables = self.rows = 0

    def handle_data(self, text):
        self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.tables += 1
        if tag == 'tr':
            self.rows += 1
        if tag == 'br':
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('td', 'th', 'tr', 'table') or tag.startswith('hd'):
            self.parts.append('\n')


def validate(source, target):
    raw = source.read_bytes()
    original = json.loads(raw.decode('utf-8'))
    prepared = json.loads(target.read_text(encoding='utf-8'))
    prefix = target.name.removesuffix('_prepared.json')
    record = json.loads((target.parent / 'Record' / f'{prefix}_reocrd').read_text(encoding='utf-8'))
    if prepared['input_sha256'] != hashlib.sha256(raw).hexdigest():
        raise ValueError('來源雜湊不符')
    if len(original['chunks']) != len(prepared['chunks']):
        raise ValueError('chunk數量不符')
    number = re.compile(r'(?<!\w)-?\d[\d,]*(?:\.\d+)?')
    tables = rows = 0
    counts = Counter()
    for before, after in zip(original['chunks'], prepared['chunks']):
        if before != after['original_chunk'] or before['chunk_id'] != after['chunk_id']:
            raise ValueError('原文／順序／識別碼改變')
        meta = after['metadata']
        if ('report_year' in meta or meta['page'] != before['page'] or
                meta['years'] != before['years'] or
                any(type(v) is not int for v in meta['years'] + meta['page'])):
            raise ValueError('metadata型別或內容不符')
        visible = Visible()
        visible.feed(before['content'])
        tables += visible.tables
        rows += visible.rows
        old_numbers = Counter(number.findall(''.join(visible.parts)))
        new_numbers = Counter(number.findall(after['embedding_text']))
        if old_numbers - new_numbers:
            raise ValueError(f'{before["chunk_id"]}數字出現次數不足')
        if after['preparation']['token_count'] is not None:
            raise ValueError('尚未選定模型卻填入token數')
        counts[before['content_type']] += 1
    for info in record['outputs'].values():
        if hashlib.sha256((target.parent / info['filename']).read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('輸出雜湊不符')
    markdown = target.with_suffix('.md').read_text(encoding='utf-8')
    if len(re.findall(r'^\| ', markdown, re.M)) != rows + tables:
        raise ValueError('pipe表格列數不符')
    return {'chunk_count': len(prepared['chunks']), 'counts_by_type': dict(counts),
            'html_tables': tables, 'html_rows': rows, 'pipe_lines': rows + tables,
            'original_chunks_unchanged': True, 'numeric_occurrences_preserved': True,
            'hashes_match': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('prepared', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.source, args.prepared), ensure_ascii=False, indent=2))
