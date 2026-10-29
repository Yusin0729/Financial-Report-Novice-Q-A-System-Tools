"""共用結構→策略→資料契約；不寫檔、不呼叫模型。"""
from copy import deepcopy
from config.chunking import SEMANTIC_SCHEMA_VERSION as SCHEMA, SEMANTIC_RULE_VERSION as RULE
from functions.chunking.parser import parse_tagged
from functions.chunking.sections import classify_section_events, chunk_section_fields
from functions.chunking.semantic_structure import build_structure, size, DESCRIPTION, _protected_starts
from functions.chunking.table_metadata import table_years, table_completeness, with_document_year

def title_tree(atoms):
    root, nodes = None, {}
    for atom in atoms:
        parent = None
        for level, title, key in atom.path:
            if key not in nodes:
                node = {'level': level, 'text': title, 'children': []}
                nodes[key] = node
                if parent is None:
                    if root is not None:
                        raise ValueError('同一chunk跨越不同hd2，未合併不相關章節')
                    root = node
                else:
                    parent['children'].append(node)
            parent = nodes[key]
    return {'main_title': atoms[0].main, 'heading': root}


def unique_records(atoms, name):
    values = {}
    for atom in atoms:
        for record in getattr(atom, name):
            values[record['start']] = record
    return [deepcopy(v) for _, v in sorted(values.items())]


def make_item(atoms, identity, doc_id, reason):
    year, _ = identity
    tables = [a for a in atoms if a.kind == 'table']
    content = ''.join(a.content for a in atoms)
    title = title_tree(atoms)
    years, sources = [], []
    if tables:
        periods = []
        for atom in tables:
            periods.extend(atom.periods)
        years, sources = table_years(''.join(a.content for a in tables), periods, year)
    years, sources = with_document_year(years, sources, year)
    result = {'chunk_id': '', 'doc_id': doc_id, 'years': years,
              'page': sorted({p for a in atoms for p in a.pages}), 'title': title,
              'data_tags': [], 'content_type': 'table' if tables else 'text', 'content': content,
              'body_char_count': size(content), 'source_spans': [s for a in atoms for s in a.spans],
              'cut_reason': reason, 'parent_id': None, 'part_index': None,
              'table_context': tables[0].context if tables else '',
              'appendix_id': next((a.appendix_id for a in atoms if a.appendix_id), None),
              'year_sources': sources, 'table_year': unique_records(atoms, 'table_year'),
              'directions': unique_records(atoms, 'directions'),
              'table_ids': [f'{doc_id}__table_{a.spans[0]["start"]}' for a in tables]}
    result.update(chunk_section_fields(title))
    if tables:
        result['table_completeness'] = table_completeness(content)
    return result


def chunk_hierarchical(text, *, identity, source_sha256, config,
                       legacy_page_snapshots=False, legacy_empty_hd=False):
    events = classify_section_events(parse_tagged(text, expected_identity=identity,
        legacy_page_snapshots=legacy_page_snapshots, legacy_empty_hd=legacy_empty_hd), text)
    roots = build_structure(events, text, strict_blocks=True)
    from functions.chunking.parent_child import chunk_parent_child
    return chunk_parent_child(roots,text,identity=identity,source_sha256=source_sha256,config=config)
