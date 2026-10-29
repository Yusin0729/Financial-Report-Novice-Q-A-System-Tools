"""辨識有表頭分隔列的Markdown管線表格；不猜散落數字的欄列。"""
import re


def cells(line):
    body = line.strip()
    if not (body.startswith('|') and body.endswith('|')):
        return None
    return [part.strip().replace(r'\|', '|') for part in re.split(r'(?<!\\)\|', body)[1:-1]]


def pipe_tables(text, excluded=()):
    lines = text.splitlines(keepends=True)
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    found, index = [], 0
    while index + 1 < len(lines):
        header, separator = cells(lines[index]), cells(lines[index+1])
        if (index in excluded or index+1 in excluded or not header or not separator
                or len(header) != len(separator)
                or not all(re.fullmatch(r':?-+:?', c.strip()) for c in separator)):
            index += 1
            continue
        end = index + 2
        while end < len(lines) and end not in excluded and cells(lines[end]) is not None:
            end += 1
        found.append((starts[index], starts[end] if end < len(lines) else len(text), index, end))
        index = end
    return found
