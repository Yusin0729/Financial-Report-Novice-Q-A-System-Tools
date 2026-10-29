"""共用階層、段落及不可拆分語意範圍；不決定embedding或寫檔。"""
import re
from dataclasses import dataclass, field
from html import unescape
from functions.chunking.table_parents import preceding_heading, preceding_periods, appendix_groups
from functions.markdown_processing.mark_headings import _protected_lines

DESCRIPTION = re.compile(r'<(?P<kind>table_year|table_direction|content_direction)>(?P<text>.*?)</(?P=kind)>')
LIST_ITEM = re.compile(r'^[ \t\u3000]*###(?!#)[ \t\u3000]*\S')
CONTROL = re.compile(r'<!--.*?-->|</?(?:page_start|page_end|content_start|content_end|table_start|table_end|fulltablestart)>')


def size(content):
    value = re.sub(r'<[^>]*>|<!--.*?-->', '', content, flags=re.S)
    value = re.sub(r'(?m)^[ \t]*#{1,6}[ \t]*', '', unescape(value))
    return sum(not c.isspace() for c in value)


@dataclass
class Atom:
    content: str
    spans: list
    pages: list
    path: tuple
    main: str
    kind: str = 'text'
    directions: tuple = ()
    table_year: tuple = ()
    context: str = ''
    periods: tuple = ()
    list_item: bool = False
    appendix_id: str | None = None

    @property
    def weight(self):
        return size(self.content)


@dataclass
class Unit:
    atoms: list
    special: bool = False
    reason: str = 'paragraph'

    @property
    def weight(self):
        return sum(a.weight for a in self.atoms)


@dataclass
class Node:
    path: tuple
    main: str
    parts: list = field(default_factory=list)
    audit: bool = False

    def atoms(self):
        return [a for p in self.parts for a in (p.atoms() if isinstance(p, Node) else [p])]

    @property
    def weight(self):
        return sum(a.weight for a in self.atoms())


def _protected_starts(source):
    lines = source.splitlines(keepends=True)
    protected = _protected_lines(source, lines)
    result, offset = set(), 0
    for i, line in enumerate(lines):
        if i in protected:
            result.add(offset)
        offset += len(line)
    return result


def _table_content(event, *, by_page=False):
    """只去除外層獨立控制行；表格格內、候選與程式碼原文保護。"""
    lines = event.text.splitlines(keepends=True)
    html_ranges,full_ranges,code_lines = [],[],set()
    protected = _protected_lines(event.text, lines,table_ranges=html_ranges,
                                 full_table_ranges=full_ranges,code_lines=code_lines)
    segments = event.source_parts or ((event.start, event.end),)
    # 將event局部索引映回原tagged；接續表的非連續來源同樣可追溯。
    intervals, base = [], 0
    for first, last in segments:
        intervals.append((base, base + last-first, first))
        base += last-first
    pieces, spans, offset = [], [], 0
    current_page = event.page
    for index, line in enumerate(lines):
        marker = re.fullmatch(r'<!-- Page: \d+_\d{4}_P([1-9]\d*) -->', line.rstrip('\r\n'))
        source_page = (by_page and marker and index not in code_lines and
                       not any(a<=offset<b for a,b in html_ranges+full_ranges))
        if source_page:
            current_page = int(marker[1])
        if not source_page and (index in protected or not CONTROL.fullmatch(line.strip())):
            pieces.append(line)
            for lo, hi, raw in intervals:
                left, right = max(offset, lo), min(offset+len(line), hi)
                if left < right:
                    spans.append({'start': raw+left-lo, 'end': raw+right-lo,
                                  'pages': [current_page] if by_page else list(event.pages)})
        offset += len(line)
    return ''.join(pieces), spans


def build_structure(events, source, *, strict_blocks=False):
    """HD範圍共享；description延續到新HD／新說明，###延續到新HD。"""
    roots, stack, path = [], [], []
    current = None
    main = ''
    directions, annual = (), ()
    pending = []
    protected = _protected_starts(source)
    appendices = {group['index']: group for group in appendix_groups(events, source)}
    appendix = None

    def root(audit=False):
        nonlocal current
        current = Node(tuple(path), main, audit=audit)
        roots.append(current)
        return current

    def flush():
        if pending:
            content = ''.join(e.text for e in pending)
            if content.strip():
                node = current if current is not None else root()
                node.parts.append(Atom(content,
                    [{'start': e.start, 'end': e.end, 'pages': [e.page]} for e in pending],
                    sorted({e.page for e in pending if e.page is not None}), tuple(path), main,
                    directions=directions, table_year=annual,
                    list_item=any(e.start not in protected and LIST_ITEM.match(e.text) for e in pending),
                    appendix_id=appendix))
            pending.clear()

    for index, event in enumerate(events):
        if index in appendices:
            flush()
            appendix = appendices[index]['id']
            # 每份附表仍是獨立完整語意單位；不由內部HD拆開。
            if not strict_blocks:
                current = root()
                stack = [current]
        if event.kind in ('section', 'main'):
            flush()
            label = event.title if event.kind == 'section' else event.text
            if label != main:
                main = label
                current, stack, path = None, [], []
                directions, annual, appendix = (), (), None
        elif event.kind in ('heading', 'audit_heading'):
            flush()
            level = 2 if event.kind == 'audit_heading' else event.level
            path = [p for p in path if p[0] < level] + [(level, event.title, event.start)]
            directions, annual = (), ()
            if appendix and not strict_blocks:
                continue
            while stack and stack[-1].path and stack[-1].path[-1][0] >= level:
                stack.pop()
            node = Node(tuple(path), main, audit=event.kind == 'audit_heading')
            if stack:
                stack[-1].parts.append(node)
            else:
                roots.append(node)
            stack.append(node)
            current = node
            if event.kind == 'audit_heading':
                pending.append(event)
        elif event.kind == 'content_end':
            flush()
        elif event.kind == 'table':
            flush()
            node = current if current is not None else root()
            content, spans = _table_content(event, by_page=strict_blocks)
            node.parts.append(Atom(content, spans, list(event.pages), tuple(path), main, 'table',
                directions, annual, preceding_heading(events, event.start, source),
                tuple(preceding_periods(events, event.start, source)), appendix_id=appendix))
        elif event.kind == 'body':
            match = DESCRIPTION.fullmatch(event.text.strip()) if event.start not in protected else None
            if match:
                flush()
                record = {'kind': match['kind'], 'text': unescape(match['text']),
                          'start': event.start, 'end': event.end}
                if match['kind'] == 'table_year':
                    annual = (record,)
                else:
                    directions = (record,)
            elif event.text.strip() or pending:
                pending.append(event)
        # page事件不截斷段落或綁定範圍。
    flush()
    return roots


def semantic_units(atoms):
    """合併互相重疊的綁定範圍；不可把###中間的表格抽走。"""
    if not atoms:
        return []
    if atoms[0].appendix_id:
        return [Unit(atoms, True, 'appendix')]
    if any(a.path != atoms[0].path for a in atoms):
        result, run = [], []
        for atom in atoms:
            if run and atom.path != run[0].path:
                result.extend(semantic_units(run))
                run = []
            run.append(atom)
        return result + semantic_units(run)
    intervals = []
    for i, atom in enumerate(atoms):
        if atom.directions:
            key = atom.directions[0]['start']
            end = i+1
            while end < len(atoms) and atoms[end].directions and atoms[end].directions[0]['start'] == key:
                end += 1
            intervals.append((i, end, 'direction_binding'))
        if atom.list_item:
            intervals.append((i, len(atoms), 'body_list_group'))
        if atom.kind == 'table':
            intervals.append((i, i+1, 'complete_table'))
    merged = []
    for start, end, reason in sorted(intervals):
        if merged and start < merged[-1][1]:
            previous = merged.pop()
            merged.append((previous[0], max(end, previous[1]),
                           'body_list_group' if 'body_list_group' in (reason, previous[2]) else previous[2]))
        else:
            merged.append((start, end, reason))
    result, cursor = [], 0
    for start, end, reason in merged:
        result.extend(Unit([a]) for a in atoms[cursor:start])
        result.append(Unit(atoms[start:end], True, reason))
        cursor = end
    result.extend(Unit([a]) for a in atoms[cursor:])
    return result
