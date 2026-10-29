"""processed 階段清除表格及程式碼外的獨立印刷頁碼行，不讀寫檔案。"""
import re
from config.markdown_headings import PAGE_NUMBER_PATTERN
from functions.markdown_processing.mark_headings import _protected_lines
from functions.markdown_processing.page_markers import parse_page_marker

CLEANUP_VERSION = 'standalone-page-cleanup/1.2'
_FOOTER = re.compile(PAGE_NUMBER_PATTERN)
_BARE_NUMBER = re.compile(r'[ \t\u3000]*[0-9](?:[ \t\u3000]*[0-9])*[ \t\u3000]*')


def remove_standalone_page_numbers(text: str) -> tuple[str, tuple[dict, ...]]:
    lines = text.splitlines(keepends=True)
    tables, code_lines = [], set()
    protected = _protected_lines(text, lines, table_ranges=tables, code_lines=code_lines)
    # 頁序註解本身屬保護區；僅接受獨立標記，不接受表格／程式碼／多行註解內的假標記。
    comment_ranges = [(m.start(), m.end()) for m in re.finditer(r'<!--[\s\S]*?-->', text)
                      if '\n' in m[0] or '\r' in m[0]]
    markers, offset = [], 0
    for index, line in enumerate(lines):
        if (index not in code_lines and not any(a <= offset < b for a, b in tables)
                and not any(a <= offset < b for a, b in comment_ranges)):
            page = parse_page_marker(line.rstrip('\r\n'))
            if page is not None:
                markers.append((index, page))
        offset += len(line)
    bare_footers = set()
    for ordinal, (start, page) in enumerate(markers):
        end = markers[ordinal+1][0] if ordinal+1 < len(markers) else len(lines)
        last = end - 1
        while last > start and not lines[last].strip():
            last -= 1
        value = lines[last].rstrip('\r\n')
        if (last > start and last not in protected and _BARE_NUMBER.fullmatch(value)
                and int(re.sub(r'\s+', '', value)) == page):
            bare_footers.add(last)
    output, removed = [], []
    for index, line in enumerate(lines):
        if index not in protected and (_FOOTER.fullmatch(line.rstrip('\r\n')) or index in bare_footers):
            removed.append({'source_line': index + 1, 'text': line.rstrip('\r\n')})
        else:
            output.append(line)
    return ''.join(output), tuple(removed)
