"""在標記與行號紀錄完成後清理疑似表格；不改辨識門檻及候選外內容。"""
import re

from functions.markdown_processing.mark_headings import _protected_lines, _TAG

VERSION = 'suspected-table-whitespace/1.0'
_HORIZONTAL = re.compile(r'[^\S\r\n]+')


def _clean_line(line):
    parts, cursor = [], 0
    for tag in _TAG.finditer(line):
        parts.extend((_HORIZONTAL.sub('', line[cursor:tag.start()]), tag[0]))
        cursor = tag.end()
    parts.append(_HORIZONTAL.sub('', line[cursor:]))
    return ''.join(parts)


def clean_suspected_table_spaces(text):
    lines = text.splitlines(keepends=True)
    ranges = []
    # 共用已驗證的候選邊界；程式碼、HTML與註解中的假標記不採用。
    _protected_lines(text, lines, full_table_ranges=ranges)
    report = {'version': VERSION, 'block_count': len(ranges), 'changed_block_count': 0,
              'removed_whitespace_count': 0, 'removed_blank_lines': 0}
    pieces, cursor = [], 0
    for start, end in ranges:
        pieces.append(text[cursor:start])
        block = text[start:end].splitlines(keepends=True)
        inner = block[1:-1]
        # 候選常以Tab／空格對齊金額，不能把縮排資料誤當Markdown程式碼。
        # 保護判斷僅用去縮排副本；實際HTML、註解與fenced code原文不改。
        probe = [line.lstrip(' \t') for line in inner]
        protected = _protected_lines(''.join(probe), probe)
        output = [block[0]]
        for index, line in enumerate(inner):
            if index in protected:
                output.append(line)
                continue
            cleaned = _clean_line(line)
            report['removed_whitespace_count'] += len(line) - len(cleaned)
            if not cleaned.strip():
                report['removed_blank_lines'] += 1
                continue
            output.append(cleaned)
        output.append(block[-1])
        cleaned_block = ''.join(output)
        report['changed_block_count'] += cleaned_block != text[start:end]
        pieces.append(cleaned_block)
        cursor = end
    pieces.append(text[cursor:])
    return ''.join(pieces), report
