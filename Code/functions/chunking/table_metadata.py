"""表格檢索脈絡與明列年度；不把表內交易日期或金額當年度欄名。"""
import re
import unicodedata
from html import unescape
from html.parser import HTMLParser
from config.markdown_headings import APPENDIX_MARKDOWN_PATTERN
from config.table_metadata import (
    ROC_YEAR_OFFSET, ROC_YEAR_RANGE, GREGORIAN_YEAR_RANGE,
    YEAR_TOKEN, EXPLICIT_PERIOD_PATTERN, EXPLICIT_DATE_PATTERN,
)

APPENDIX_HEADING = re.compile(APPENDIX_MARKDOWN_PATTERN)
_PERIOD = re.compile(EXPLICIT_PERIOD_PATTERN)
_DATE = re.compile(EXPLICIT_DATE_PATTERN)
_YEAR = re.compile(YEAR_TOKEN)


def table_completeness(content):
    """僅標示是否含既有cannotfindtable標記，不宣稱表格品質已驗證。"""
    return 0 if '<cannotfindtable>' in content else 1


def _year_number(token):
    digits = str.maketrans('〇零○一二三四五六七八九', '000123456789')
    value = token.translate(digits)
    if value.isascii() and value.isdigit():
        return int(value)
    # 中文位值寫法，如一百一十四；逐字寫法一一四由上方處理。
    total = digit = 0
    for char in value:
        if char.isascii() and char.isdigit():
            digit = int(char)
        elif char in '十百':
            total += (digit or 1) * {'十': 10, '百': 100}[char]
            digit = 0
        else:
            return None
    return total + digit


def explicit_years(value):
    """在完整說明中找明列年／日期；民國與中文數字一律轉西元。"""
    compact = re.sub(r'\s+', '', unicodedata.normalize('NFKC', unescape(value)))
    spans = [m.group(0) for m in _PERIOD.finditer(compact)]
    spans.extend(m['year'] for m in _DATE.finditer(compact))
    if re.fullmatch(r'(?:19|20|21)\d{2}', compact):
        spans.append(compact)
    years = set()
    for raw in spans:
        for token in _YEAR.findall(raw):
            number = _year_number(token)
            if number is None:
                continue
            if ROC_YEAR_RANGE[0] <= number <= ROC_YEAR_RANGE[1]:
                years.add(number + ROC_YEAR_OFFSET)
            elif GREGORIAN_YEAR_RANGE[0] <= number <= GREGORIAN_YEAR_RANGE[1]:
                years.add(number)
    return sorted(years)


class HeaderPeriods(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table = self.row = 0
        self.cell = None
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.table += 1
            if self.table == 1:
                self.row = 0
        elif tag == 'tr' and self.table == 1:
            self.row += 1
        elif tag in ('th', 'td') and self.table == 1:
            self.cell = [tag, []]

    def handle_data(self, data):
        if self.cell is not None:
            self.cell[1].append(data)

    def handle_endtag(self, tag):
        if tag in ('th', 'td') and self.cell is not None:
            value = ''.join(self.cell[1]).strip()
            if self.row == 1 or self.cell[0] == 'th':
                self.values.append((value, f'table_header_row_{self.row}'))
            self.cell = None
        elif tag == 'table':
            self.table -= 1


def with_document_year(years, sources, file_year):
    """缺少檔名年度就追加；不取代已辨識年度，不把補入值冒充表頭來源。"""
    year = int(file_year)
    if year in years:
        return years, sources
    source = 'document_year_included' if years else 'document_year_fallback'
    return sorted(set(years) | {year}), [*sources, {'raw': str(file_year), 'source': source, 'years': [year]}]


def table_years(content, preceding_periods, file_year):
    """表頭優先；僅無年度時讀取已按邊界篩選的前置標籤。"""
    parser = HeaderPeriods()
    parser.feed(content)
    values = parser.values
    from functions.markdown_processing.pipe_tables import pipe_tables, cells
    lines = content.splitlines(keepends=True)
    for _, _, start, _ in pipe_tables(content):
        values.extend((value, 'markdown_table_header') for value in cells(lines[start]))
    sources, years = [], set()
    for raw, source in values:
        found = explicit_years(raw)
        if found:
            sources.append({'raw': raw, 'source': source, 'years': found})
            years.update(found)
    if years:
        return sorted(years), sources
    for raw, source in preceding_periods:
        found = explicit_years(raw)
        if found:
            return found, [{'raw': raw, 'source': source, 'years': found}]
    return with_document_year([], [], file_year)
