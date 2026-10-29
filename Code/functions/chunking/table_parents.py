"""完整表／附表作父項，按可靠PDF頁序建立搜尋子塊；HTML不切列。"""
import re
from copy import deepcopy
from html import unescape
from functions.chunking.table_metadata import APPENDIX_HEADING, table_years, table_completeness
from functions.markdown_processing.mark_headings import _protected_lines
from functions.chunking.sections import title_context_before


def appendix_groups(events, source):
    lines = source.splitlines(keepends=True)
    protected = _protected_lines(source, lines)
    starts, pos = {}, 0
    for i, line in enumerate(lines):
        starts[pos] = i
        pos += len(line)
    groups = []
    for i, event in enumerate(events):
        if event.kind != 'body' or starts.get(event.start) in protected:
            continue
        match = APPENDIX_HEADING.fullmatch(event.text.rstrip('\r\n'))
        if match:
            appendix_id = '附表' + re.sub(r'\s+', '', match['number'])
            if not groups or groups[-1]['id'] != appendix_id:
                groups.append({'index': i, 'id': appendix_id, 'title': match['title']})
    return groups


def _protected_starts(source):
    lines = source.splitlines(keepends=True)
    protected = _protected_lines(source, lines)
    protected_starts, offset = set(), 0
    for i, line in enumerate(lines):
        if i in protected:
            protected_starts.add(offset)
        offset += len(line)
    return protected_starts


def preceding_heading(events, position, source):
    protected_starts = _protected_starts(source)
    for event in reversed(events):
        if event.start >= position:
            continue
        if event.kind in ('section', 'main'):
            return ''
        if event.kind == 'heading':
            return event.title
        if event.kind != 'body' or not event.text.strip():
            continue  # 表格、頁碼、邊界與控制註解不阻止往前找。
        if event.start not in protected_starts:
            match = _DESCRIPTION_TAG.fullmatch(event.text.strip())
            if match:
                if match['kind'] in ('table_direction', 'content_direction'):
                    return unescape(match['text'])
    return ''


_DESCRIPTION_TAG = re.compile(
    r'<(?P<kind>table_year|table_direction|content_direction)>(?P<text>.*?)</(?P=kind)>')


def preceding_periods(events, position, source):
    """與表格說明分開：正文、另一表、hd或區域界線均阻止年度回查。"""
    values = []
    protected_starts = _protected_starts(source)
    for event in reversed(events):
        if event.start >= position:
            continue
        if event.kind in ('heading', 'audit_heading', 'table', 'section', 'main'):
            break
        if event.kind != 'body' or not event.text.strip():
            continue
        if event.start in protected_starts:
            break
        match = _DESCRIPTION_TAG.fullmatch(event.text.strip())
        if not match:
            break
        values.append((unescape(match['text']), 'preceding_' + match['kind']))
    return values


def _slice_spans(spans, first, last):
    output, offset = [], 0
    for span in spans:
        length = span['end'] - span['start']
        left, right = max(first, offset), min(last, offset + length)
        if left < right:
            output.append({'start': span['start'] + left - offset,
                           'end': span['start'] + right - offset, 'pages': span['pages']})
        offset += length
    if offset < last:
        raise ValueError('表格來源區間不足，未猜測子塊位置')
    return output


def _parts_by_page(parent):
    content = parent['content']
    lines = content.splitlines(keepends=True)
    ranges, code_lines = [], set()
    _protected_lines(content, lines, table_ranges=ranges, code_lines=code_lines)
    cuts, offset = [(0, parent['page'][0])], 0
    for i, line in enumerate(lines):
        marker = re.fullmatch(r'<!-- Page: \d+_\d{4}_P([1-9]\d*) -->', line.rstrip('\r\n'))
        in_table = any(a <= offset < b for a, b in ranges)
        if marker and i not in code_lines and not in_table and int(marker[1]) != cuts[-1][1]:
            cuts.append((offset, int(marker[1])))
        offset += len(line)
    parts = []
    for i, (start, page) in enumerate(cuts):
        end = cuts[i+1][0] if i+1 < len(cuts) else len(content)
        raw = content[start:end]
        if re.sub(r'<!--.*?-->|<[^>]*>', '', raw, flags=re.S).strip() or '<table' in raw.lower():
            parts.append((start, end, page))
        elif parts:
            left, _, previous = parts[-1]
            parts[-1] = (left, end, previous)  # 純邊界留在前塊，不冒充下一頁的內容。
    return parts


def enrich_tables(chunks, events, groups, source, identity, doc_id, contexts):
    year, _ = identity
    parents, output, issues = [], [], []
    candidates = list(chunks)
    for ordinal, group in enumerate(groups):
        end = groups[ordinal+1]['index'] if ordinal+1 < len(groups) else len(events)
        selected = events[group['index']:end]
        selected = [e for e in selected if e.kind in ('body', 'heading', 'table', 'page')]
        table_events = [e for e in selected if e.kind == 'table']
        if not table_events:
            raise ValueError(f'{group["id"]}沒有表格；附表範圍待確認，未輸出假完整附表')
        spans, pieces, pages = [], [], set()
        for event in selected:
            parts = event.source_parts or ((event.start, event.end),)
            pieces.append(event.text)
            for a, b in parts:
                spans.append({'start': a, 'end': b, 'pages': list(event.pages or (event.page,))})
            if event.kind != 'page' and event.text.strip():
                pages.update(event.pages or (event.page,))
        candidates.append({'doc_id': doc_id, 'years': [int(year)], 'page': sorted(pages),
                           'title': title_context_before(events, group['index']),
                           'data_tags': [], 'content_type': 'table', 'content': ''.join(pieces),
                           'body_char_count': 0, 'source_spans': spans, 'cut_reason': 'complete_appendix',
                           'appendix_id': group['id'], 'table_context': group['title']})
    for item in candidates:
        item = deepcopy(item)
        item.update(parent_id=None, part_index=None)
        item.setdefault('appendix_id', None)
        item.setdefault('table_context', '')
        item['year_sources'] = []
        if item['content_type'] != 'table':
            item['years'] = [int(year)]
            output.append(item)
            continue
        # 附表也以第一張實際表的位置尋找說明，不能把附表編號當作hd。
        start = item['source_spans'][0]['start']
        position = next((e.start for e in events if e.kind == 'table' and e.start >= start
                         and any(s['start'] <= e.start < s['end'] for s in item['source_spans'])), start)
        item['table_context'] = preceding_heading(events, position, source)
        item['years'], item['year_sources'] = table_years(
            item['content'], preceding_periods(events, position, source), year)
        item['table_completeness'] = table_completeness(item['content'])
        parent_id = f'{doc_id}__t{len(parents)+1:05d}'
        parent = {**deepcopy(item), 'chunk_id': parent_id}
        parents.append(parent)
        parts = _parts_by_page(parent)
        resolved = sorted({p for _, _, p in parts}) == parent['page']
        if not resolved:
            issues.append({'parent_id': parent_id, 'status': 'unresolved_page_boundary', 'pages': parent['page']})
            parts = [(0, len(parent['content']), None)]
        for number, (start, end, page) in enumerate(parts, 1):
            child = deepcopy(item)
            child.update(parent_id=parent_id, part_index=number, content=item['content'][start:end],
                         page=[page] if page is not None else item['page'],
                         source_spans=_slice_spans(item['source_spans'], start, end), cut_reason='parent_page')
            from functions.markdown_processing.pipe_tables import pipe_tables
            child['content_type'] = 'table' if (re.search(
                r'<table\b|^[ \t\u3000]*<cannotfindtable>[ \t\u3000]*\r?$', child['content'], re.I | re.M)
                                               or pipe_tables(child['content'])) else 'text'
            if page is not None:
                for span in child['source_spans']:
                    span['pages'] = [page]
            if child['content_type'] == 'text':
                child['years'], child['year_sources'] = [int(year)], []
                child.pop('table_completeness', None)
            else:
                child['table_completeness'] = table_completeness(child['content'])
            output.append(child)
    new_contexts = {}
    for number, item in enumerate(output, 1):
        previous_id = item.get('chunk_id')
        item['chunk_id'] = f'{doc_id}__c{number:05d}'
        new_contexts[item['chunk_id']] = contexts.get(previous_id, ())
    return output, parents, issues, new_contexts
