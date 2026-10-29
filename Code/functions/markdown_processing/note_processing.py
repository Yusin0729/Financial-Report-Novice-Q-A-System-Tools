"""第二階段只處理獨立 <note> 之後的附註，前段逐字保留。"""
from dataclasses import replace

from functions.markdown_processing.mark_headings import (
    _protected_lines, mark_missing_headings, recheck_dash_number_headings,
)
from functions.markdown_processing.page_cleanup import remove_standalone_page_numbers
from functions.markdown_processing.suspected_tables import detect_suspected_tables, detection_report
from functions.markdown_processing.body_lists import mark_body_lists, heading_line_origins
from functions.markdown_processing.intercharacter_spaces import clean_intercharacter_spaces
from functions.markdown_processing.suspected_table_spaces import clean_suspected_table_spaces

SCOPE_VERSION = 'note-only/1.0'


def process_note_content(text, *, clean_pages=True):
    lines = text.splitlines(keepends=True)
    protected = _protected_lines(text, lines)
    markers = [i for i, line in enumerate(lines)
               if i not in protected and line.strip() == '<note>']
    if not markers:
        raise ValueError('缺少有效的獨立 <note> 標記；第二階段未處理該份文件')
    if len(markers) != 1:
        raise ValueError('存在多個有效 <note> 標記，無法唯一確定附註範圍')
    offset = markers[0] + 1
    prefix = ''.join(lines[:offset])
    suffix = ''.join(lines[offset:])
    detected, candidates, line_map = detect_suspected_tables(suffix)
    marked = mark_missing_headings(detected)
    listed, list_changes, list_report = mark_body_lists(marked.markdown)
    origins = heading_line_origins(detected, marked.changes)
    list_changes = tuple(replace(c, line_number=origins[c.line_number-1]+1)
                         for c in list_changes)
    for gap in list_report['gaps']:
        gap['line_number'] = line_map[origins[gap['line_number']-1]]+offset
    rechecked = recheck_dash_number_headings(listed)
    final_changes = tuple(replace(c, line_number=origins[c.line_number-1]+1)
                          for c in rechecked.changes)
    cleaned, removed = (remove_standalone_page_numbers(rechecked.markdown)
                        if clean_pages else (rechecked.markdown, ()))
    # 最後清理，既有偵測／補標題紀錄仍對應清理前的來源位置。
    cleaned, suspected_whitespace_report = clean_suspected_table_spaces(cleaned)
    normalized, whitespace_report = clean_intercharacter_spaces(prefix + cleaned)
    result = replace(marked, markdown=normalized,
                     changes=tuple(replace(c, line_number=line_map[c.line_number - 1] + offset)
                                   for c in (*marked.changes, *list_changes, *final_changes)))
    removed = tuple({**item, 'source_line': item['source_line'] + offset} for item in removed)
    scope = {'version': SCOPE_VERSION, 'marker_line': offset,
             'first_content_line': offset + 1, 'prefix_preserved': True}
    candidates = tuple({**item, 'start_line': item['start_line'] + offset,
                        'end_line': item['end_line'] + offset} for item in candidates)
    scope['suspected_table_detection'] = detection_report(candidates)
    scope['body_list_classification'] = list_report
    scope['final_dash_number_recheck'] = {'changed_count': len(final_changes)}
    scope['intercharacter_space_cleanup'] = whitespace_report
    scope['suspected_table_whitespace_cleanup'] = suspected_whitespace_report
    return result, removed, scope
