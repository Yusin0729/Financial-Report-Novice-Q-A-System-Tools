"""依明確來源標記辨識區域與查核報告標題，不推測文件章節。"""
import re
from dataclasses import replace
from html import unescape

from functions.markdown_processing.mark_headings import _protected_lines

_MARKERS = {'<會計師查核報告>': '會計師查核報告',
            '<note>': '合併財務報告附註',
            '<合併財務報告附註>': '合併財務報告附註'}
_AUDIT_HEADING = re.compile(r'^[ \t\u3000]*##(?!#)[ \t\u3000]*(\S[^\r\n]*)$')


def classify_section_events(events, source):
    """保留原位置及文字；只標註section／audit_heading事件供切塊端使用。"""
    lines = source.splitlines(keepends=True)
    protected = _protected_lines(source, lines)
    protected_starts, offset = set(), 0
    for index, line in enumerate(lines):
        if index in protected:
            protected_starts.add(offset)
        offset += len(line)
    section = ''
    result = []
    for event in events:
        if event.kind == 'body' and event.start not in protected_starts:
            value = event.text.strip()
            if value in _MARKERS:
                section = _MARKERS[value]
                result.append(replace(event, kind='section', title=section))
                continue
            match = _AUDIT_HEADING.fullmatch(event.text.rstrip('\r\n'))
            if section == '會計師查核報告' and match:
                result.append(replace(event, kind='audit_heading', title=unescape(match[1])))
                continue
        result.append(event)
    return tuple(result)


def chunk_section_fields(title):
    """由既有標題樹取得多條真實路徑，絕不把同層項目串成父子。"""
    root = title['heading']
    paths = []

    def visit(node, ancestors):
        path = ancestors+[node['text']]
        if not node['children']:
            paths.append(' > '.join(path))
        for child in node['children']:
            visit(child, path)

    if root and title['main_title'] != '會計師查核報告':
        for child in root['children']:
            visit(child, [])
    return {'main_section': title['main_title'],
            'sub_section': root['text'] if root else '', 'note_title': paths}


def title_context_before(events, index):
    """附表的章節仍取其真實所屬hd2／動態路徑，不以附表名假造hd2。"""
    main, stack = '', {}
    for event in events[:index]:
        if event.kind in ('section', 'main'):
            label = event.title if event.kind == 'section' else event.text
            if label != main:
                stack.clear()
            main = label
        elif event.kind in ('heading', 'audit_heading'):
            level = 2 if event.kind == 'audit_heading' else event.level
            stack = {k: v for k, v in stack.items() if k < level}
            stack[level] = event.title
    root = parent = None
    for level, text in sorted(stack.items()):
        node = {'level': level, 'text': text, 'children': []}
        if parent is None:
            root = node
        else:
            parent['children'].append(node)
        parent = node
    return {'main_title': main, 'heading': root}
