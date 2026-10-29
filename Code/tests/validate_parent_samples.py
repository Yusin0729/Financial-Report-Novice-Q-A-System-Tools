"""唯讀實際processed樣本，在記憶體驗證tagged→chunk→prepared；不執行OCR或API。"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Code'))
from schemas import TaggingMetadata
from functions.markdown_processing.comment_tagging import tag_comments
from functions.markdown_processing.mark_headings import _protected_lines
from functions.chunking.chunks import chunk_tagged
from Code_2.functions.embedding.prepare import prepare_document
from Code_2.functions.embedding.load_prepared import validate_prepared


def html_tables(text):
    spans = []
    _protected_lines(text, text.splitlines(keepends=True), table_ranges=spans)
    return Counter(text[a:b] for a, b in spans)


def run():
    for batch, stock in [('Financial_20261022_01-23-16', '2330'), ('Financial_20261023_17-27-05', '2379')]:
        source = ROOT / 'Output' / 'markdown_processed' / batch / f'2025_{stock}_processed.md'
        original = source.read_bytes()
        tagged = tag_comments(original.decode('utf-8'), None, TaggingMetadata(report_year='2025', stock_code=stock)).markdown
        result = chunk_tagged(tagged, identity=('2025', stock), source_sha256=hashlib.sha256(tagged.encode()).hexdigest())
        doc = result.document
        expected = html_tables(tagged[result.excluded_prefix_end:])
        actual = Counter()
        for parent in doc['parents']:
            actual.update(html_tables(parent['content']))
        assert actual == expected, 'HTML表格未逐字完整保留'
        prepared = prepare_document(doc, input_sha256='a'*64)
        validate_prepared(prepared)
        assert source.read_bytes() == original, '來源被修改'
        print(json.dumps({'stock': stock, 'chunks': len(doc['chunks']), 'parents': len(doc['parents']),
                          'appendices': [p['appendix_id'] for p in doc['parents'] if p['appendix_id']],
                          'html_tables_preserved': sum(actual.values()), 'issues': doc['issues'],
                          'multi_year_chunks': sum(len(c['years']) > 1 for c in doc['chunks']),
                          'prepared_chunks': len(prepared['chunks'])}, ensure_ascii=False))


if __name__ == '__main__':
    run()
