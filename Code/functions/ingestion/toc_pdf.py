"""原PDF唯讀抽頁與目錄JSON驗證；不載入Docling／OCR，不寫Output。"""
import hashlib
import json
from io import BytesIO
from pathlib import Path

from config.toc import TOC_SCHEMA_VERSION
from schemas import TocPdf, TocResult, TOC_RESPONSE_SCHEMA


def extract_toc_pdf(source: Path, pages: tuple[int, ...] = (2, 3)) -> TocPdf:
    import pypdfium2 as pdfium
    if pages != (2, 3):
        raise ValueError('本版僅授權擷取實體第2、3頁')
    # 從同一份bytes取得雜湊及抽頁，避免檔案中途被修改造成來源錯配。
    original = source.read_bytes()
    with pdfium.PdfDocument(original) as pdf:
        count = len(pdf)
        if count < max(pages):
            raise ValueError('PDF不足3頁，未抽頁或傳送')
        with pdfium.PdfDocument.new() as selected:
            selected.import_pages(pdf, pages=[p-1 for p in pages])
            stream = BytesIO()
            selected.save(stream)
    data = stream.getvalue()
    with pdfium.PdfDocument(data) as check:
        if len(check) != 2:
            raise ValueError('抽頁驗證失敗，未傳送')
    return TocPdf(data, hashlib.sha256(original).hexdigest(),
                  hashlib.sha256(data).hexdigest(), count, pages)


def load_prepared_toc_pdf(path: Path, *, source_sha256: str,
                          extracted_sha256: str, source_page_count: int,
                          source_pages: tuple[int, ...]) -> TocPdf:
    """載入第一階段已抽出的兩頁；來源頁序必須由紀錄提供，不由檔名猜測。

    純本機驗證，不呼叫 API，也不修改來源或寫入 Output。
    """
    import pypdfium2 as pdfium
    import re
    if source_pages != (2, 3) or type(source_page_count) is not int or source_page_count < 3:
        raise ValueError('抽頁來源紀錄必須對應原PDF實體第2、3頁及有效總頁數')
    if not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
               for value in (source_sha256, extracted_sha256)):
        raise ValueError('抽頁來源紀錄缺少有效 SHA-256，未傳送')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != extracted_sha256:
        raise ValueError('目錄PDF與第一階段紀錄雜湊不一致，未傳送')
    with pdfium.PdfDocument(data) as pdf:
        if len(pdf) != 2:
            raise ValueError('目錄PDF必須恰有兩頁，未傳送')
    return TocPdf(data, source_sha256, extracted_sha256, source_page_count, source_pages)


def _validate_shape(value, schema, path='toc'):
    expected = schema['type']
    types = {'object': dict, 'array': list, 'string': str, 'integer': int}
    if type(value) is not types[expected]:
        raise ValueError(f'{path}型別錯誤')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path}不在允許值內')
    if expected == 'object':
        if set(value) != set(schema['required']):
            raise ValueError(f'{path}欄位缺少或多餘')
        for key, child in value.items():
            _validate_shape(child, schema['properties'][key], f'{path}.{key}')
    if expected == 'array':
        for index, child in enumerate(value):
            _validate_shape(child, schema['items'], f'{path}[{index}]')


def validate_toc(value: dict, source_pages=(2, 3)) -> str:
    _validate_shape(value, TOC_RESPONSE_SCHEMA)
    if tuple(p['source_pdf_page'] for p in value['pages']) != tuple(source_pages):
        raise ValueError('頁面分類須逐一對應原PDF第2、3頁，不可缺頁或重複')
    classes = {p['source_pdf_page']: p['classification'] for p in value['pages']}
    ids = set()
    covered = set()
    last_page = 0
    for entry in value['entries']:
        page = entry['source_pdf_page']
        if classes.get(page) != 'toc':
            raise ValueError('非目錄／無法辨識頁不得輸出目錄項目')
        if page < last_page:
            raise ValueError('目錄項目來源頁序倒置')
        last_page = page
        if not entry['id'].strip() or entry['id'] in ids or not entry['title'].strip():
            raise ValueError('目錄id重複、空白id或空白標題')
        if entry['parent_id'] and entry['parent_id'] not in ids:
            raise ValueError('目錄父項不存在或順序錯誤')
        ids.add(entry['id'])
        covered.add(page)
    if any(p['classification'] == 'toc' and p['source_pdf_page'] not in covered for p in value['pages']):
        raise ValueError('目錄頁沒有任何項目，不視為成功')
    if any(p['classification'] == 'unreadable' and not p['issues'] for p in value['pages']):
        raise ValueError('無法辨識頁須記錄原因')
    if any(p['classification'] == 'unreadable' for p in value['pages']):
        return 'incomplete_needs_review'
    return 'extracted_needs_review' if value['entries'] else 'no_toc_found'


def parse_response(response: dict, pdf: TocPdf) -> TocResult:
    if response.get('promptFeedback', {}).get('blockReason'):
        raise ValueError('Gemini拒絕處理輸入，未產生有效目錄')
    candidates = response.get('candidates', [])
    if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
        reason = candidates[0].get('finishReason', 'missing') if candidates else 'missing'
        # MAX_TOKENS不能以可解析的片段當完整成功。
        raise ValueError(f'Gemini未完整結束（{reason}），不輸出成功目錄')
    text = ''.join(p.get('text', '') for p in candidates[0].get('content', {}).get('parts', [])
                   if not p.get('thought', False))
    if not text.strip():
        raise ValueError('Gemini回答為空白')
    value = json.loads(text)
    status = validate_toc(value, pdf.source_pages)
    if any(entry['parent_id'] or entry['note_numbers'] for entry in value['entries']):
        raise ValueError('本版 Gemini 僅允許目錄大標，parent_id 與 note_numbers 必須留空')
    toc = {'schema_version': TOC_SCHEMA_VERSION, 'source_sha256': pdf.source_sha256,
           'source_pages': list(pdf.source_pages), 'status': status,
           'extraction_mode': 'main_titles', **value}
    return TocResult(toc, response, text, status)
