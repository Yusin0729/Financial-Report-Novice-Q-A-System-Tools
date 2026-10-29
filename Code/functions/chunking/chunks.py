"""公開切塊入口、JSON契約及Markdown輸出。

chunk_tagged使用共用語意結構與雙模式4.0；chunk_tagged_legacy保留3.x回歸，
不匯入原始參考碼，不作第三種介面模式。表格及綁定內容始終完整保存。
"""
import re
from copy import deepcopy
from dataclasses import dataclass
from html import escape, unescape
from config.chunking import CHUNK_RULE_VERSION, CHUNK_SCHEMA_VERSION, ChunkSettings
from config.markdown_blocks import DESCRIPTION_TAG_LINE, FULL_TABLE_START
from functions.chunking.parser import parse_tagged
from functions.markdown_processing.page_markers import format_page_marker
from functions.chunking.table_parents import appendix_groups, enrich_tables
from functions.chunking.sections import classify_section_events, chunk_section_fields
from functions.chunking.table_metadata import table_completeness
from functions.content_context import content_body, validate_context_modes, SCHEMA as CONTEXT_SCHEMA
from functions.parent_relations import SCHEMA as HIERARCHY_SCHEMA, validate_relations

_UNITS = re.compile(r'<!--.*?-->|<(?=/?[A-Za-z])(?:"[^"]*"|\x27[^\x27]*\x27|[^\x27"<>])*>|&(?:#\d+|#x[0-9a-fA-F]+|\w+);|.', re.S)


def visible_units(text):
    """傳回原字元結尾位置、可見字數、可見字元；HTML/實體不切半。"""
    for match in _UNITS.finditer(text):
        raw = match[0]
        visible = '' if raw.startswith('<') and len(raw) > 1 and raw.endswith('>') else unescape(raw)
        yield match.end(), sum(not c.isspace() for c in visible), visible


@dataclass(frozen=True)
class ChunkResult:
    document: dict
    markdown: str
    excluded_prefix_end: int


def validate_chunk_document(document):
    """獨立的chunk schema檢查；不得使用目錄JSON schema。"""
    if document.get('schema_version') not in (CHUNK_SCHEMA_VERSION, 'financial-chunks/4.0', CONTEXT_SCHEMA, HIERARCHY_SCHEMA) or not isinstance(document.get('chunks'), list):
        raise ValueError('不是有效的chunk JSON')
    validate_context_modes(document)
    seen = set()
    parents = {p['chunk_id']: p for p in document.get('parents', [])}
    if len(parents) != len(document.get('parents', [])):
        raise ValueError('父表識別碼重複')
    for chunk in document['chunks'] + list(parents.values()):
        required = {'chunk_id', 'doc_id', 'years', 'page', 'title', 'data_tags', 'content_type',
                    'content', 'body_char_count', 'source_spans', 'cut_reason', 'parent_id', 'part_index',
                    'table_context', 'appendix_id', 'year_sources', 'main_section', 'sub_section', 'note_title'}
        if chunk.get('content_type') == 'table':
            required.add('table_completeness')
        if document['schema_version'] in ('financial-chunks/4.0', CONTEXT_SCHEMA, HIERARCHY_SCHEMA):
            required.update(('table_year', 'directions', 'table_ids'))
        if document['schema_version'] in (CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
            required.add('content_prefix')
            if not content_body(chunk).strip():
                raise ValueError('content首行後缺少正文')
        if document['schema_version']==HIERARCHY_SCHEMA:
            required.update(('node_type','parent_relation','heading_parent_id'))
        if 'embedding_context_modes' in document:
            required.add('embedding_context_mode')
        if set(chunk) != required:
            raise ValueError('chunk欄位缺少或多餘')
        if chunk['chunk_id'] in seen or chunk['doc_id'] != document['doc_id']:
            raise ValueError('chunk識別碼重複或文件錯配')
        seen.add(chunk['chunk_id'])
        if chunk['parent_id'] is not None and (chunk['parent_id'] not in parents or
                type(chunk['part_index']) is not int or chunk['part_index'] < 1):
            raise ValueError('子塊沒有可靠父表／順序')
        if (chunk['content_type'] not in ('text', 'table') and not
                (chunk['content_type']=='mixed' and chunk.get('node_type')=='heading_parent')) or not isinstance(chunk['content'], str) or not chunk['content'].strip():
            raise ValueError('chunk內容或類型無效')
        if chunk['content_type'] == 'table' and (
                type(chunk['table_completeness']) is not int
                or chunk['table_completeness'] != table_completeness(chunk['content'])):
            raise ValueError('table_completeness與表格標記不符，須為整數0或1')
        if (not chunk['page'] or chunk['page'] != sorted(set(chunk['page'])) or
                any(type(p) is not int or p < 1 for p in chunk['page'])):
            raise ValueError('chunk頁序清單無效')
        if not chunk['years'] or any(type(y) is not int for y in chunk['years']) or chunk['data_tags'] != []:
            raise ValueError('chunk年份／data_tags格式無效')
        if type(chunk['body_char_count']) is not int or chunk['body_char_count'] < 0:
            raise ValueError('chunk字數無效')
        def heading(node, parent_level=1):
            if set(node) != {'level', 'text', 'children'} or type(node['level']) is not int or node['level'] <= parent_level:
                raise ValueError('標題樹層級無效')
            if not isinstance(node['text'], str) or not node['text'].strip() or not isinstance(node['children'], list):
                raise ValueError('標題樹內容無效')
            for child in node['children']:
                heading(child, node['level'])
        title = chunk['title']
        if set(title) != {'main_title', 'heading'} or not isinstance(title['main_title'], str):
            raise ValueError('chunk標題格式無效')
        if title['heading'] is not None:
            if title['heading']['level'] != 2:
                raise ValueError('chunk根標題層級無效')
            heading(title['heading'])
        if any(chunk[key] != value for key, value in chunk_section_fields(title).items()):
            raise ValueError('章節欄位與實際標題階層不符')
        if not chunk['source_spans']:
            raise ValueError('chunk缺少來源位置')
        for span in chunk['source_spans']:
            if set(span) != {'start', 'end', 'pages'} or not 0 <= span['start'] < span['end']:
                raise ValueError('chunk來源位置無效')
        if document['schema_version'] in ('financial-chunks/4.0', CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
            if (not isinstance(chunk['table_ids'], list)
                    or any(not isinstance(value, str) or not value for value in chunk['table_ids'])
                    or len(set(chunk['table_ids'])) != len(chunk['table_ids'])):
                raise ValueError('表格識別清單無效或重複')
            for field in ('table_year', 'directions'):
                if not isinstance(chunk[field], list) or any(not isinstance(r, dict)
                    or set(r) != {'kind', 'text', 'start', 'end'}
                    or r['kind'] not in ('table_year', 'table_direction', 'content_direction')
                    or not isinstance(r['text'], str) or type(r['start']) is not int
                    or type(r['end']) is not int or not 0 <= r['start'] < r['end'] for r in chunk[field]):
                    raise ValueError('語意說明／年度來源格式無效')
    if document['schema_version']==HIERARCHY_SCHEMA:
        validate_relations(document)
    if document['schema_version'] in ('financial-chunks/4.0', CONTEXT_SCHEMA):
        for parent_id, parent in parents.items():
            children = sorted((c for c in document['chunks'] if c['parent_id'] == parent_id),
                              key=lambda c: c['part_index'])
            if (parent['parent_id'] is not None or not children
                    or [c['part_index'] for c in children] != list(range(1,len(children)+1))
                    or ''.join(content_body(c) for c in children) != content_body(parent)
                    or sorted({p for c in children for p in c['page']}) != parent['page']):
                raise ValueError('直接父子範圍不完整、重複或多層關聯')


def chunk_tagged_legacy(text, *, identity, source_sha256, config=ChunkSettings(),
                 legacy_page_snapshots=False, legacy_empty_hd=False):
    if config.target_characters < 1 or config.grace_page_offset < 0 or config.sentence_end != '。':
        raise ValueError('chunk字數／跨頁設定無效，句號只允許中文。')
    year, stock = identity
    doc_id = f'{year}{config.document_period}_{stock}_Financial_Report'
    events = parse_tagged(text, expected_identity=identity, legacy_page_snapshots=legacy_page_snapshots,
                          legacy_empty_hd=legacy_empty_hd)
    events = classify_section_events(events, text)
    groups = appendix_groups(events, text)
    appendix_start = groups[0]['index'] if groups else len(events)
    start = 0
    main = ''
    for event in events[:start]:
        if event.kind == 'main':
            main = event.text
    stack = {}
    chunks, pieces, spans, pages = [], [], [], []
    count = 0
    reached_page = None
    tree = None
    tree_nodes = {}
    body_page = None
    chunk_main = ''
    has_body = False
    markdown_contexts = {}
    chunk_prefix = ()
    prefix_selected = False

    def include_path():
        nonlocal tree
        parent = None
        for level, (title, key) in sorted(stack.items()):
            if key not in tree_nodes:
                node = {'level': level, 'text': title, 'children': []}
                tree_nodes[key] = node
                if parent is None:
                    tree = node
                else:
                    parent['children'].append(node)
            parent = tree_nodes[key]

    def add(raw, event, *, start_offset=None, end_offset=None, body=True):
        nonlocal body_page, chunk_main, has_body, chunk_prefix, prefix_selected
        if not raw:
            return
        if not pieces:
            chunk_main = main
        if raw.strip() and not prefix_selected:
            # 只補在新塊起點繼承的祖先；實際出現的新標題由原content保留，不重列。
            chunk_prefix = tuple((level, title) for level, (title, _) in sorted(stack.items())
                                 if level > 2 and (event.kind != 'heading' or level < event.level))
            prefix_selected = True
        include_path()
        if body and event.page is not None and body_page != event.page:
            pieces.append(format_page_marker(event.page, identity) + '\n')
            body_page = event.page
        pieces.append(raw)
        if raw.strip():
            if body:
                has_body = True
            for page in event.pages or (event.page,):
                if page is not None and page not in pages:
                    pages.append(page)
        first = event.start if start_offset is None else start_offset
        last = event.end if end_offset is None else end_offset
        if first < last:
            spans.append({'start': first, 'end': last, 'pages': list(event.pages or (event.page,))})

    def finish(reason):
        nonlocal pieces, spans, pages, count, reached_page, tree, tree_nodes, body_page, has_body, chunk_prefix, prefix_selected
        if has_body:
            markdown_contexts[f'{doc_id}__c{len(chunks)+1:05d}'] = chunk_prefix
            chunks.append({'chunk_id': f'{doc_id}__c{len(chunks)+1:05d}', 'doc_id': doc_id,
                           'years': [int(year)], 'page': sorted(pages),
                           'title': {'main_title': chunk_main, 'heading': deepcopy(tree)},
                           'data_tags': [], 'content_type': 'text', 'content': ''.join(pieces),
                           'body_char_count': count, 'source_spans': deepcopy(spans), 'cut_reason': reason})
        pieces, spans, pages = [], [], []
        count, reached_page, tree, tree_nodes, body_page, has_body = 0, None, None, {}, None, False
        chunk_prefix, prefix_selected = (), False

    for event in events[start:appendix_start]:
        if event.kind == 'section':
            if event.title != main:
                finish('main_section_change')
                stack.clear()
            main = event.title
            continue
        if event.kind == 'audit_heading':
            finish('audit_heading')
            stack = {2: (event.title, event.start)}
            # 原##保留在查核正文中；不建立假的hd標籤，也不計入正文字數。
            add(event.text, event, body=True)
            continue
        if event.kind == 'main':
            if event.text != main:
                finish('main_title_change')
                stack.clear()
            main = event.text
            continue
        if event.kind == 'heading':
            if event.level == 2:
                finish('hd2')
                stack.clear()
            if not stack and event.level != 2:
                raise ValueError('下層標題缺少hd2，不建立猜測的標題路徑')
            stack = {level: value for level, value in stack.items() if level < event.level}
            stack[event.level] = (event.title, event.start)
            if event.level != 2:
                add(f'<hd{event.level}>{escape(event.title, quote=False)}</hd{event.level}>\n', event, body=False)
            continue
        if event.kind in ('page', 'content_end'):
            if event.kind == 'content_end' and reached_page is not None and main != '會計師查核報告':
                finish('target_then_content_end')
            continue
        if event.page is None:
            if event.text.strip():
                raise ValueError('正文沒有可靠頁序，未推測來源位置')
            continue
        if event.kind == 'table':
            finish('before_table')
            include_path()
            markdown_contexts[f'{doc_id}__c{len(chunks)+1:05d}'] = tuple(
                (level, title) for level, (title, _) in sorted(stack.items()) if level > 2)
            chunks.append({'chunk_id': f'{doc_id}__c{len(chunks)+1:05d}', 'doc_id': doc_id,
                           'years': [int(year)], 'page': sorted(event.pages),
                           'title': {'main_title': main, 'heading': deepcopy(tree)}, 'data_tags': [],
                           'content_type': 'table', 'content': event.text, 'body_char_count': 0,
                           'source_spans': [{'start': a, 'end': b, 'pages': list(event.pages)}
                                            for a, b in (event.source_parts or ((event.start, event.end),))],
                           'cut_reason': 'complete_table'})
            tree, tree_nodes = None, {}
            continue
        if event.kind == 'body':
            # 未辨識的Markdown標題仍保存，但不計入正文字數。
            if (re.match(r'^ {0,3}#{1,6}(?:\s|$)', event.text)
                    or DESCRIPTION_TAG_LINE.fullmatch(event.text.rstrip('\r\n'))):
                # 這些行不是已解析的hd metadata；即使緊接表格也不可當空內容丟棄。
                add(event.text, event, body=True)
                continue
            cursor = 0
            for end, weight, visible in visible_units(event.text):
                count += weight
                if main != '會計師查核報告' and reached_page is None and count >= config.target_characters:
                    reached_page = event.page
                if (reached_page is not None and event.page >= reached_page + config.grace_page_offset
                        and config.sentence_end in visible):
                    add(event.text[cursor:end], event, start_offset=event.start+cursor, end_offset=event.start+end)
                    finish('grace_page_sentence')
                    cursor = end
            add(event.text[cursor:], event, start_offset=event.start+cursor)
    finish('eof')
    chunks, parents, issues, markdown_contexts = enrich_tables(
        chunks, events, groups, text, identity, doc_id, markdown_contexts)
    for item in chunks+parents:
        item.update(chunk_section_fields(item['title']))
    if not chunks:
        raise ValueError('來源沒有可輸出的正文或表格')
    # 獨立保留檢查：每個非空正文來源區間必須落入某個chunk，不以空標題吞掉內容。
    covered = sorted((s['start'], s['end']) for chunk in chunks for s in chunk['source_spans'])
    position = 0
    for event in events[start:]:
        if event.kind not in ('body', 'audit_heading') or not event.text.strip():
            continue
        cursor = event.start
        while position < len(covered) and covered[position][1] <= cursor:
            position += 1
        check = position
        while cursor < event.end and check < len(covered) and covered[check][0] <= cursor:
            cursor = max(cursor, covered[check][1])
            check += 1
        if cursor < event.end:
            raise ValueError(f'正文來源區間{event.start}:{event.end}未完整保留，不輸出部分chunk')
    document = {'schema_version': CHUNK_SCHEMA_VERSION, 'rule_version': CHUNK_RULE_VERSION,
                'doc_id': doc_id, 'source_sha256': source_sha256,
                'excluded_prefix_end': 0, 'chunks': chunks, 'parents': parents, 'issues': issues}
    validate_chunk_document(document)
    return ChunkResult(document, render_chunks(document, markdown_contexts), 0)


def chunk_tagged(text, *, identity, source_sha256, config=ChunkSettings(),
                 legacy_page_snapshots=False, legacy_empty_hd=False):
    """新版兩模式入口；3.3演算法另留明確legacy函式供舊資料回歸。"""
    from functions.chunking.hierarchical import chunk_hierarchical
    return chunk_hierarchical(text, identity=identity, source_sha256=source_sha256, config=config,
        legacy_page_snapshots=legacy_page_snapshots, legacy_empty_hd=legacy_empty_hd)


def render_chunks(document, contexts):
    out = []
    modern = document['schema_version'] in ('financial-chunks/4.0', CONTEXT_SCHEMA,HIERARCHY_SCHEMA)
    for chunk in document['chunks']:
        out.extend([f'<!-- chunk_id: {chunk["chunk_id"]} -->\n', f'<!-- doc_id: {chunk["doc_id"]} -->\n',
                    f'<!-- years: {", ".join(map(str, chunk["years"]))} -->\n',
                    f'<!-- page: {", ".join(map(str, chunk["page"]))} -->\n'])
        for key, values in (('Main_Section', [chunk['main_section']]),
                            ('Sub_Section', [chunk['sub_section']]),
                            ('Note_Title', chunk['note_title'] or [''])):
            for value in values:
                if '\n' in value or '\r' in value:
                    raise ValueError('章節標籤含換行，未擅自合併')
                # HTML註解內的>可直接顯示；保留層級分隔符而不輸出&gt;。
                out.append(f'<!-- {key}: {value.replace("--", "&#45;&#45;")} -->\n')
        # 文字與表格皆顯示父子欄位；未建立父子關係時保持空值。
        fields = ('parent_id','part_index','parent_relation','heading_parent_id') if document['schema_version']==HIERARCHY_SCHEMA else ('parent_id','part_index')
        for field in fields:
            value = chunk.get(field)
            out.append(f'<!-- {field}: {"" if value is None else value} -->\n')
        if chunk['content_type'] == 'table':
            out.append(f'<!-- table_completeness: {chunk["table_completeness"]} -->\n')
        for field in ('appendix_id', 'table_context'):
            value = chunk.get(field)
            if value is not None and value != '':
                # 脈絡可能含註解保留字；以HTML實體安全呈現，不改JSON原值。
                safe = escape(str(value), quote=False).replace('--', '&#45;&#45;')
                out.append(f'<!-- {field}: {safe} -->\n')
        if modern:
            for record in chunk['table_year']:
                out.append('<!-- table_year: ' + escape(record['text'], quote=False).replace('--', '&#45;&#45;') + ' -->\n')
            for record in chunk['directions']:
                out.append('<!-- ' + record['kind'] + ': ' + escape(record['text'], quote=False).replace('--', '&#45;&#45;') + ' -->\n')
        table = chunk['content_type'] == 'table'
        inherited = ''.join(f'<hd{level}>{escape(title, quote=False)}</hd{level}>\n'
                            for level, title in contexts.get(chunk['chunk_id'], ()))
        if table:
            out.append(inherited)
        full = table and re.search(r'^[ \t\u3000]*<cannotfindtable>[ \t\u3000]*\r?$', chunk['content'], re.M)
        out.append((FULL_TABLE_START+'\n' if full else '<table_start>\n') if table else '<content_start>\n')
        if not table:
            out.append(inherited)
        out.append(chunk['content'])
        if not chunk['content'].endswith(('\n', '\r')):
            out.append('\n')
        out.append('<table_end>\n\n' if table else '</content_end>\n\n')
    return ''.join(out)
