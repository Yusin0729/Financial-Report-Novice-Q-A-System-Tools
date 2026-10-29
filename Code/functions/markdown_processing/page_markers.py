"""頁序格式共用讀寫；Page 的 P 為 PDF 實體頁序，非印刷頁碼。"""
import re

_CURRENT = re.compile(r'^\s*<!-- Page: (?P<stock>[0-9]+)_(?P<year>[0-9]{4})_P(?P<page>[1-9][0-9]*) -->\s*$')
_LEGACY = re.compile(r'^\s*<!-- PDF_PAGE: (?P<page>[1-9][0-9]*) -->\s*$')


def format_page_marker(page: int, identity=None) -> str:
    if type(page) is not int or page < 1:
        raise ValueError('PDF 實體頁序必須為正整數')
    if identity is None:
        return f'<!-- PDF_PAGE: {page} -->'
    year, stock = identity
    if not re.fullmatch(r'[0-9]{4}', year) or not re.fullmatch(r'[0-9]+', stock):
        raise ValueError('頁序標籤缺少有效年份或股票代號')
    return f'<!-- Page: {stock}_{year}_P{page} -->'


def parse_page_marker(line: str, *, expected_identity=None):
    match = _CURRENT.fullmatch(line.lstrip('\ufeff'))
    if match:
        identity = (match['year'], match['stock'])
        if expected_identity is not None and identity != expected_identity:
            raise ValueError('Page 頁序標籤的年份或股票代號與文件不符')
        return int(match['page'])
    match = _LEGACY.fullmatch(line.lstrip('\ufeff'))
    return int(match['page']) if match else None
