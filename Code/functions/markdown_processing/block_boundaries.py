"""替已產生章節註解的 Markdown 加區塊邊界；不刪改來源字元。

依外層 HTML table 精確字元區間處理，避免把同行內文混入表格。
插入獨立標籤前若原文未換行，補上的分隔換行另行計數。
頁面與內容各自追蹤，可交錯跨頁；接續詞命中的表格群保留完整HTML與中間原文。
"""
import re
from bisect import bisect_right
from config.markdown_blocks import CONTENT_START, CONTENT_END, TABLE_START, FULL_TABLE_START, TABLE_END, PAGE_START, PAGE_END
from config.markdown_blocks import HD_TAG_LINE, DESCRIPTION_TAG_LINE
from functions.markdown_processing.mark_headings import _protected_lines
from functions.markdown_processing.page_markers import parse_page_marker
from functions.markdown_processing.table_continuation import group_continued_tables


def add_block_boundaries(text: str, *, page_prefaces: dict[int, str] | None = None,
                         continuation_joins: list[dict] | None = None) -> tuple[str, dict[str, int], int]:
    lines = text.splitlines(keepends=True)
    ranges, full_ranges, code_lines = [], [], set()
    protected = _protected_lines(text, lines, table_ranges=ranges, code_lines=code_lines,
                                 full_table_ranges=full_ranges)
    # 候選原文若含已辨識的內部表格，以外層候選為準，不重複包裝。
    ranges = sorted([r for r in ranges if not any(a <= r[0] and r[1] <= b
                                                 for a, b in full_ranges)] + full_ranges)
    offsets, offset = [], 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    table_lines = set()
    for start, end in ranges:
        table_lines.update(range(bisect_right(offsets, start) - 1, bisect_right(offsets, end - 1)))
    comment_lines = protected - code_lines - table_lines
    markers = {CONTENT_START, CONTENT_END, TABLE_START, FULL_TABLE_START, TABLE_END, PAGE_START, PAGE_END}
    for index, line in enumerate(lines):
        if index not in protected and line.strip() in markers:
            raise ValueError('來源已有區塊標籤，拒絕重複加入')
    groups, joins = group_continued_tables(text, ranges, offsets, code_lines)
    if continuation_joins is not None:
        continuation_joins.extend(joins)
    out = []
    counts = {'page': 0, 'table': 0, 'content': 0}
    added_newlines = 0
    page_open = False
    content_open = False
    active_main = None

    def tag(value):
        nonlocal added_newlines
        if out and not out[-1].endswith(('\n', '\r')):
            out.append('\n')
            added_newlines += 1
        out.append(value + '\n')

    def flush_content():
        nonlocal content_open
        if content_open:
            tag(CONTENT_END)
            content_open = False

    def main_title(line, *, in_table=False):
        nonlocal active_main
        match = re.fullmatch(r'<!-- MAIN_TITLE: (.*?) -->', line.rstrip('\r\n'))
        if match:
            if match[1] != active_main and not in_table:
                flush_content()
            active_main = match[1]

    def normal(raw, start, *, in_table=False):
        nonlocal page_open, content_open
        offset = start
        for line in raw.splitlines(keepends=True):
            index = bisect_right(offsets, offset) - 1
            body = line.rstrip('\r\n')
            page = parse_page_marker(body) if index not in code_lines else None
            if page is not None:
                preface = page_prefaces.get(page) if page_prefaces else None
                if preface:
                    main_title(preface, in_table=in_table)
                if page_open:
                    tag(PAGE_END)
                if preface:
                    tag(preface)
                out.append(line)  # 頁序在頁區塊之外，先輸出Page再開啟page_start。
                tag(PAGE_START)
                counts['page'] += 1
                page_open = True
            elif in_table:
                out.append(line)
            elif index in comment_lines:
                main_title(line)
                out.append(line)
            elif index not in code_lines and (re.match(r'^ {0,3}#{1,6}(?:[ \t]+|$)', body)
                    or HD_TAG_LINE.fullmatch(body) or DESCRIPTION_TAG_LINE.fullmatch(body)):
                flush_content()
                out.append(line)
            else:
                # 空白行原樣保留，不結束content；只有結構邊界或EOF才收尾。
                if line.strip() and not content_open:
                    tag(CONTENT_START)
                    content_open = True
                    counts['content'] += 1
                out.append(line)
            offset += len(line)

    cursor = 0
    for group in groups:
        start = group[0][0]
        normal(text[cursor:start], cursor)
        flush_content()
        full = any(span in full_ranges for span in group)
        tag(FULL_TABLE_START if full else TABLE_START)
        previous_end = start
        for table_start, end in group:
            normal(text[previous_end:table_start], previous_end, in_table=True)
            out.append(text[table_start:end])
            previous_end = end
        tag(TABLE_END)
        counts['table'] += 1
        if full:
            counts['full_table'] = counts.get('full_table', 0)+1
        cursor = end
    normal(text[cursor:], cursor)
    flush_content()
    if page_open:
        tag(PAGE_END)
    return ''.join(out), counts, added_newlines
