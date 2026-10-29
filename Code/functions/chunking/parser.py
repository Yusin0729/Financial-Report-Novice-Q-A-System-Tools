"""解析獨立的page與content/table狀態；頁面可跨越內容邊界。

保留來源字元位置與完整表格；不沿用舊parser在換頁時flush內文的行為。
"""
import re
from bisect import bisect_right
from dataclasses import dataclass
from html import unescape
from config.markdown_blocks import (
    HD_TAG_LINE, CONTENT_START, CONTENT_END, TABLE_START, FULL_TABLE_START, TABLE_END, PAGE_START, PAGE_END,
)
from functions.markdown_processing.mark_headings import _protected_lines
from functions.markdown_processing.page_markers import parse_page_marker
from functions.markdown_processing.table_continuation import group_continued_tables

IDENTITY_PAGE = re.compile(r'^<!-- Page: (?P<stock>\d+)_(?P<year>\d{4})_P(?P<page>[1-9]\d*) -->$')


@dataclass(frozen=True)
class Event:
    kind: str
    text: str
    start: int
    end: int
    page: int | None
    pages: tuple[int, ...] = ()
    level: int | None = None
    title: str = ''
    source_parts: tuple[tuple[int, int], ...] = ()


def parse_tagged(text, *, expected_identity, legacy_page_snapshots=False, legacy_empty_hd=False):
    lines = text.splitlines(keepends=True)
    ranges, full_ranges, code_lines = [], [], set()
    _protected_lines(text, lines, table_ranges=ranges, code_lines=code_lines,
                     full_table_ranges=full_ranges)
    offsets, offset = [], 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    table_lines = set()
    for start, end in ranges:
        table_lines.update(range(bisect_right(offsets, start) - 1, bisect_right(offsets, end - 1)))
    full_lines = set()
    for start, end in full_ranges:
        full_lines.update(range(bisect_right(offsets, start)-1, bisect_right(offsets, end-1)))
    events = []
    page = None
    page_open = content_open = False
    table_start = None
    table_pages = []
    in_comment = False
    seen_identity = None
    page_header = False
    ignored_spans = []
    for index, line in enumerate(lines):
        start, end = offsets[index], offsets[index] + len(line)
        body = line.rstrip('\r\n').lstrip('\ufeff')
        comment_literal = in_comment
        literal = index in table_lines or index in full_lines or index in code_lines or in_comment
        if not literal and '<!--' in body and '-->' not in body:
            in_comment = True
            literal = True
            comment_literal = True
        elif in_comment and '-->' in body:
            in_comment = False
        match = IDENTITY_PAGE.fullmatch(body) if not literal else None
        if match:
            identity = (match['year'], match['stock'])
            if identity != expected_identity or (seen_identity and seen_identity != identity):
                raise ValueError('Page年份／股票代號與文件不符')
            seen_identity = identity
            number = int(match['page'])
            if page is not None and number <= page:
                raise ValueError('Page頁序重複或倒置')
            page = number
            page_header = True
            if table_start is not None:
                if page not in table_pages:
                    table_pages.append(page)
            else:
                events.append(Event('page', line, start, end, page))
            continue
        if not literal and parse_page_marker(body) is not None:
            raise ValueError('chunk需要含股票代號及年份的Page標記；請重新產生新版tagged')
        if not literal and body in (PAGE_START, PAGE_END):
            if body == PAGE_START:
                if page_open:
                    raise ValueError('page_start重複或上一頁未結束')
                page_open = True
            else:
                if not page_open:
                    raise ValueError('多餘page_end')
                page_open = False
            continue
        if table_start is not None:
            if not literal and body == TABLE_END:
                events.append(Event('table', text[table_start:start], table_start, start,
                                    table_pages[0], tuple(table_pages)))
                table_start = None
                table_pages = []
            elif not literal and body in (TABLE_START, FULL_TABLE_START, CONTENT_START, CONTENT_END):
                raise ValueError('table區塊內含重複或衝突的內容邊界')
            continue
        if not literal and body in (TABLE_START, FULL_TABLE_START):
            if content_open or page is None:
                raise ValueError('table起點與content衝突或沒有可靠頁序')
            table_start, table_pages = end, [page]
            page_header = False
            continue
        if not literal and body == TABLE_END:
            raise ValueError('多餘table_end')
        if not literal and body in (CONTENT_START, CONTENT_END):
            opening = body == CONTENT_START
            if opening == content_open:
                raise ValueError('content邊界重複或不成對')
            content_open = opening
            page_header = False
            if not opening:
                events.append(Event('content_end', '', start, end, page))
            continue
        if index in table_lines:
            raise ValueError('HTML表格缺少完整table_start／table_end包裝')
        heading = HD_TAG_LINE.fullmatch(body) if not literal else None
        if heading:
            if legacy_empty_hd and not heading['title'].strip():
                ignored_spans.append((start, end))
                if int(heading['level']) == 2:
                    page_header = False
                continue
            if legacy_page_snapshots and page_header and int(heading['level']) == 2:
                # 舊版固定在Page／MAIN_TITLE後輸出一個目前小標快照，非新標題。
                ignored_spans.append((start, end))
                page_header = False
                continue
            if not heading['title'].strip():
                raise ValueError('來源仍含空白hd標籤，請重新產生新版tagged')
            events.append(Event('heading', line, start, end, page,
                                level=int(heading['level']), title=unescape(heading['title'])))
            page_header = False
        elif not literal and re.fullmatch(r'<!-- MAIN_TITLE: .* -->', body):
            events.append(Event('main', body[len('<!-- MAIN_TITLE: '):-len(' -->')], start, end, page))
        elif not comment_literal and (literal or not body.startswith('<!--')):
            events.append(Event('body', line, start, end, page))
            if body.strip():
                page_header = False
    if table_start is not None or content_open or page_open:
        raise ValueError('tagged頁面／內文／表格邊界未完成，不輸出部分chunk')
    if seen_identity is None:
        raise ValueError('缺少含年份及股票代號的Page頁序')
    return join_table_events(text, events, offsets, code_lines, ignored_spans)


def join_table_events(text, events, offsets, code_lines, ignored_spans):
    """chunk端再次依接續詞分組，亦支援舊tagged每頁分開包裝的表格。"""
    table_events = [e for e in events if e.kind == 'table']
    ranges = [(e.start, e.end) for e in table_events]
    groups, _ = group_continued_tables(text, ranges, offsets, code_lines)
    by_start = {e.start: e for e in table_events}
    replacements = {}
    for group in groups:
        if len(group) == 1:
            continue
        first, last = by_start[group[0][0]], by_start[group[-1][0]]
        parts = [(first.start, first.end)]
        pages = list(first.pages)
        for previous, current in zip(group, group[1:]):
            position = previous[1]
            for line in text[previous[1]:current[0]].splitlines(keepends=True):
                end = position + len(line)
                if (line.rstrip('\r\n') not in (CONTENT_START, CONTENT_END, TABLE_START, FULL_TABLE_START, TABLE_END)
                        and not any(a <= position and end <= b for a, b in ignored_spans)):
                    parts.append((position, end))
                position = end
            parts.append(current)
            for event in events:
                if first.start <= event.start <= current[0]:
                    for page in event.pages or ((event.page,) if event.page is not None else ()):
                        if page not in pages:
                            pages.append(page)
            for page in by_start[current[0]].pages:
                if page not in pages:
                    pages.append(page)
        replacements[first.start] = Event('table', ''.join(text[a:b] for a, b in parts),
                                          first.start, last.end, first.page, tuple(sorted(pages)),
                                          source_parts=tuple(parts))
    result = []
    skip_until = -1
    for event in events:
        if event.start < skip_until:
            continue
        if event.start in replacements:
            event = replacements[event.start]
            skip_until = event.end
        result.append(event)
    return tuple(result)
