"""從本機 Docling 目錄頁建立 PDF 實體頁序選取計畫。"""
import re
import unicodedata
from html.parser import HTMLParser
from config.page_selection import (NORMALIZATION_FORM, NOTES_HEADER_PATTERN, NOTES_REFERENCE_TERMS,
                                   NON_NOTES_PAGE_HEADINGS)


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


_RANGE = re.compile(r'^(\d+)\s*(?:[~〜～\-–—至]\s*(\d+))?$')


def _compact(value):
    return re.sub(r'\s+', '', unicodedata.normalize(NORMALIZATION_FORM, value))


def find_notes_in_body(read_page, first_page, last_page, *, audit_end=None):
    """由正文逐頁定位，優先比對公司沿革，也接受獨立附註主標。"""
    start = max(first_page, (audit_end + 1) if audit_end is not None else first_page)
    for number in range(start, last_page + 1):
        text = read_page(number)
        titles = [re.sub(r'^#{1,6}', '', _compact(line)).strip('*') for line in text.splitlines()]
        if any(title in NON_NOTES_PAGE_HEADINGS for title in titles):
            continue
        if '公司沿革' in _compact(text):
            return number, 'company_history_fallback'
        from functions.markdown_processing.mark_headings import _protected_lines
        protected = _protected_lines(text, text.splitlines(keepends=True))
        for index, title in enumerate(titles):
            if index in protected:
                continue
            if any(term in title for term in NOTES_REFERENCE_TERMS):
                continue
            if re.fullmatch(NOTES_HEADER_PATTERN, title):
                return number, 'notes_heading_fallback'
    return None, None


def _row_range(cells, maximum):
    # 只從獨立的頁碼欄讀取；標題中的數字或附註編號不視為頁碼。
    for cell in cells[1:]:
        match = _RANGE.fullmatch(_compact(cell))
        if match:
            start, end = int(match[1]), int(match[2] or match[1])
            if 1 <= start <= end <= maximum:
                return start, end
    return None


def _rows(markdown):
    parser = _Rows()
    parser.feed(markdown)
    from functions.markdown_processing.pipe_tables import pipe_tables, cells
    lines = markdown.splitlines(keepends=True)
    for _, _, start, end in pipe_tables(markdown):
        parser.rows.extend(cells(lines[i]) for i in range(start, end) if i != start+1)
    return parser.rows


def select_from_toc(page_2: str, page_3: str | None, maximum: int) -> dict:
    """回傳可核對的頁序；缺失欄位保持 None，不自行猜測。"""
    first = _rows(page_2)
    if not ('目錄' in _compact(page_2) and sum(_row_range(row, maximum) is not None for row in first) >= 3):
        raise ValueError('PDF 第2頁無法確認為可讀目錄')
    pages = [(2, first)]
    if page_3:
        third = _rows(page_3)
        numbered = sum(bool(re.match(r'^(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)])',
                                     _compact(''.join(row)))) for row in third)
        header = any('頁' in _compact(''.join(row)) and '項' in _compact(''.join(row))
                     for row in third[:2])
        if sum(_row_range(row, maximum) is not None for row in third) >= 2 and (header or numbered >= 2):
            pages.append((3, third))
    audit = notes = None
    for _, rows in pages:
        for row in rows:
            title = _compact(''.join(row))
            selected = _row_range(row, maximum)
            if '會計師查核報告' in title and selected:
                audit = selected
            if ('財務報告附註' in title or '財務報表附註' in title) and selected:
                notes = selected[0]
            elif '公司沿革' in title and selected and notes is None:
                notes = selected[0]
    if audit and notes and audit[1] >= notes:
        raise ValueError('目錄查核報告與附註頁碼重疊，未裁切')
    return {'toc_pages': [number for number, _ in pages],
            'audit_pages': audit, 'notes_start': notes}
