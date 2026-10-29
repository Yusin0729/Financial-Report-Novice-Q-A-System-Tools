"""只標記疑似漏辨識區塊，不還原表格、不更動數值或呼叫模型。"""
import unicodedata

from config.suspected_tables import (RULE_VERSION, CANDIDATE_RUN_LENGTH, BODY_RUN_LENGTH,
                                     BODY_CHINESE_LENGTH, START_TAG, END_TAG)
from functions.markdown_processing.numeric_lines import is_numeric_line
from functions.markdown_processing.mark_headings import _protected_lines, _TAG
from functions.markdown_processing.page_cleanup import remove_standalone_page_numbers
from functions.markdown_processing.page_markers import parse_page_marker


def chinese_count(value):
    value = unicodedata.normalize('NFKC', value)
    return sum(0x3400 <= ord(c) <= 0x4DBF or 0x4E00 <= ord(c) <= 0x9FFF
               or 0xF900 <= ord(c) <= 0xFAFF or 0x20000 <= ord(c) <= 0x323AF
               for c in value)


def detect_suspected_tables(text):
    """輸入為note後的原文；回傳新文、原始行號區塊及新行對原始行映射。"""
    lines = text.splitlines(keepends=True)
    protected = _protected_lines(text, lines)
    _, removed = remove_standalone_page_numbers(text)
    footers = {row['source_line'] - 1 for row in removed}
    spans = []
    active = None
    context_start = None
    candidate_run = 0
    long_lines = []
    page = None
    active_page = None

    def close(end, reason):
        nonlocal active, context_start, candidate_run, long_lines
        if active is not None:
            spans.append({'start_line': active + 1, 'end_line': end, 'pdf_pages':
                          [active_page] if active_page is not None else [],
                          'trigger': f'{CANDIDATE_RUN_LENGTH}_consecutive_candidate_lines',
                          'stop_reason': reason})
        active, context_start, candidate_run, long_lines = None, None, 0, []

    for index, line in enumerate(lines):
        value = line.strip()
        marker = parse_page_marker(value)
        if marker is not None:
            close(index, 'pdf_page_boundary')
            page = marker
            continue
        if (index in protected or index in footers or value.startswith('##')
                or _TAG.fullmatch(value)):
            close(index, 'heading_or_protected_boundary')
            continue
        if not value:
            continue
        numeric = is_numeric_line(value)
        long_body = not numeric and chinese_count(value) > BODY_CHINESE_LENGTH
        if active is None:
            if long_body:
                context_start, candidate_run = None, 0
                continue
            if context_start is None:
                context_start = index
            # 未超過20個中文字的非空行也計數，含項目名稱及金額碎片。
            # 只計數及標記，不拼接碎片、不放寬共用的完整數值判定。
            candidate_run += 1
            if candidate_run >= CANDIDATE_RUN_LENGTH:
                active, active_page = context_start, page
            continue
        if long_body:
            long_lines.append(index)
            if len(long_lines) >= BODY_RUN_LENGTH:
                close(long_lines[0], 'three_long_chinese_body_lines')
        else:
            long_lines = []
    close(len(lines), 'end_of_document')

    # 只插入獨立標記行，原有內容／空白行與換行格式保留。
    opens = {span['start_line'] - 1: span for span in spans}
    closes = {span['end_line']: span for span in spans}
    output, line_map = [], []
    for index in range(len(lines) + 1):
        if index in closes:
            span = closes[index]
            newline = '\r\n' if lines[index - 1].endswith('\r\n') else '\n'
            added_eol = not lines[index - 1].endswith(('\r', '\n'))
            if added_eol:
                output[-1] += newline
            span['added_eol'] = added_eol
            output.append(END_TAG + newline)
            line_map.append(index)
        if index in opens:
            newline = '\r\n' if lines[index].endswith('\r\n') else '\n'
            output.append(START_TAG + newline)
            line_map.append(index + 1)
        if index < len(lines):
            output.append(lines[index])
            line_map.append(index + 1)
    return ''.join(output), tuple(spans), line_map


def detection_report(candidates):
    return {'version': RULE_VERSION, 'candidate_run_length': CANDIDATE_RUN_LENGTH,
            'body_run_length': BODY_RUN_LENGTH, 'body_chinese_length': BODY_CHINESE_LENGTH,
            'candidate_count': len(candidates), 'candidates': list(candidates)}
