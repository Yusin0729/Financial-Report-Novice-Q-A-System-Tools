"""正文標題分類與區塊標記；不讀目錄、不產生MAIN_TITLE、不呼叫LLM。"""
import re
from html import escape
from config.markdown_blocks import HD_TAG_LINE, DESCRIPTION_TAG_LINE
from config.markdown_headings import (
    MARKER_PATTERNS, PURE_YEAR_PATTERN, MULTI_YEAR_DESCRIPTION_PATTERN, COLON_ENDINGS,
)
from functions.ingestion.toc_pdf import validate_toc
from functions.markdown_processing.mark_headings import _protected_lines
from functions.markdown_processing.heading_hierarchy import HeadingHierarchy
from functions.markdown_processing.page_markers import parse_page_marker
from functions.markdown_processing.block_boundaries import add_block_boundaries
from schemas import CommentTagResult, TaggingMetadata

VERSION = 'markdown-comment-tagging/3.3'
_MARKERS = tuple((kind, re.compile('^'+pattern)) for kind, pattern in MARKER_PATTERNS)
_YEAR = re.compile(PURE_YEAR_PATTERN)
_YEAR_DESCRIPTION = re.compile(MULTI_YEAR_DESCRIPTION_PATTERN)
_HEADING = re.compile(r'^[ \t\u3000]*##(?!#)[ \t\u3000]*(.*)$')
_OWN_TAG = re.compile(r'^<!-- (?:MAIN_TITLE|SUB_TITLE|HEADING_\d+|REPORT_YEAR|STOCK_CODE|COMPANY_NAME):')


def _heading_text(line):
    text = re.sub(r'^#{1,6}[ \t\u3000]*', '', line.strip())
    return re.sub(r'^-\s+', '', text).strip()


def _pages(value, maximum):
    if not value.strip():
        return set()
    result = set()
    for part in re.split(r'[、,，]', value):
        match = re.fullmatch(r'\s*(\d+)\s*(?:[~～\-–—至]\s*(\d+))?\s*', part)
        if not match:
            raise ValueError(f'未支援的目錄頁碼格式：{value}')
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= maximum:
            raise ValueError(f'目錄頁碼超出已知 PDF_PAGE 範圍：{value}')
        result.update(range(first, last + 1))
    return result


def validate_tagging_toc(toc):
    if not isinstance(toc, dict):
        raise ValueError('目錄不是JSON物件')
    if toc.get('status') != 'extracted_needs_review':
        raise ValueError('目錄不是有效待核對結果，未加標籤')
    shape = {key: toc[key] for key in ('pages', 'entries')}
    if validate_toc(shape, tuple(toc.get('source_pages', ()))) != 'extracted_needs_review':
        raise ValueError('目錄不完整，未加標籤')
    if toc.get('extraction_mode') == 'main_titles' and any(
            entry['parent_id'] or entry['note_numbers'] for entry in shape['entries']):
        raise ValueError('main_titles 目錄含非大標項目，未加標籤')


def tag_comments(text: str, toc: dict | None, metadata: TaggingMetadata) -> CommentTagResult:
    # toc僅保留舊呼叫介面相容；新流程完全不使用它作分類或大標依據。
    lines = text.splitlines(keepends=True)
    ranges = []
    code_lines = set()
    protected = _protected_lines(text, lines, table_ranges=ranges, code_lines=code_lines)
    table_lines = set()
    offset = 0
    range_index = 0
    for index, line in enumerate(lines):
        while range_index < len(ranges) and ranges[range_index][1] <= offset:
            range_index += 1
        if range_index < len(ranges) and ranges[range_index][0] < offset + len(line):
            table_lines.add(index)
        offset += len(line)
    pages = []
    for index, line in enumerate(lines):
        if index in table_lines or index in code_lines:
            continue
        body = line.rstrip('\r\n').lstrip('\ufeff')
        if _OWN_TAG.match(body) or (index not in protected and
                                  (HD_TAG_LINE.fullmatch(body) or DESCRIPTION_TAG_LINE.fullmatch(body))):
            raise ValueError('來源已有新式章節標籤，拒絕重複加入；請使用 processed 原檔')
        expected = (metadata.report_year, metadata.stock_code) if metadata.report_year and metadata.stock_code else None
        number = parse_page_marker(body, expected_identity=expected)
        if number is not None:
            if pages and number <= pages[-1][1]:
                raise ValueError('PDF_PAGE 頁序重複或倒置')
            pages.append((index, number))
    if not pages:
        raise ValueError('來源沒有可靠 PDF_PAGE，未推測頁碼')
    issues = []
    out = []

    def comment(name, value):
        if name == 'SUB_TITLE' or name.startswith('HEADING_'):
            if not value.strip():
                return  # 無目前小標時不輸出空hd；重置由內部tracker處理。
            level = 2 if name == 'SUB_TITLE' else int(name.removeprefix('HEADING_')) + 2
            if '\n' in value or '\r' in value:
                raise ValueError(f'{name} 含換行，無法寫入單行標題標籤')
            out.append(f'<hd{level}>{escape(value, quote=False)}</hd{level}>\n')
            return
        if '--' in value or '\n' in value or '\r' in value:
            raise ValueError(f'{name} 含無法安全寫入單行 HTML 註解的內容，未擅自改寫')
        out.append(f'<!-- {name}: {value} -->\n')

    comment('REPORT_YEAR', metadata.report_year)
    comment('STOCK_CODE', metadata.stock_code)
    comment('COMPANY_NAME', metadata.company_name)
    tracker = HeadingHierarchy()

    def emit_line(index):
        line = lines[index]
        # 附表####與註###由processed產生；此階段原樣保留，不再補標記。
        if index not in protected and _HEADING.fullmatch(line.rstrip('\r\n')):
            normalized = re.sub(r'\s+', '', _heading_text(line))
            marker = next((kind for kind, pattern in _MARKERS if pattern.match(normalized)), None)
            title = _heading_text(line)
            if _YEAR.fullmatch(normalized):
                out.append(f'<table_year>{escape(title, quote=False)}</table_year>\n')
                return
            if _YEAR_DESCRIPTION.fullmatch(normalized):
                out.append(f'<table_direction>{escape(title, quote=False)}</table_direction>\n')
                return
            if marker == 'chinese_comma':
                if not _MARKERS[0][1].sub('', normalized, count=1):
                    out.append(line)
                    return
                tracker.start_section(title)
                comment('SUB_TITLE', title)
                return  # 以hd標籤取代原##行，不再重複輸出標題。
            elif marker and tracker.path:
                path = tracker.add_dynamic(title, marker)
                comment(f'HEADING_{path[-1].level - 1}', title)
                return
            elif marker:
                issues.append({'status': 'dynamic_heading_without_section',
                               'source_line': index + 1, 'title': title})
            elif title.rstrip().endswith(COLON_ENDINGS):
                out.append(f'<content_direction>{escape(title, quote=False)}</content_direction>\n')
                return
        out.append(line)

    for index in range(pages[0][0]):
        emit_line(index)
    for p_index, (start, page) in enumerate(pages):
        end = pages[p_index + 1][0] if p_index + 1 < len(pages) else len(lines)
        out.append(lines[start])  # PDF_PAGE 完全沿用，不重新產生或修改。
        for index in range(start + 1, end):
            emit_line(index)
    joins = []
    bounded, counts, added_newlines = add_block_boundaries(''.join(out),
                                                         continuation_joins=joins)
    # 格式版本屬正文資料契約，chunk 不需再從實驗 Record 猜版本。
    return CommentTagResult(f'<!-- TAGGING_VERSION: {VERSION} -->\n' + bounded,
                            VERSION, (), tuple(issues), counts, added_newlines, tuple(joins))
