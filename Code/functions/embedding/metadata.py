"""中立、有型別的 metadata；向量庫未選定，暫不作庫專用轉型。"""
from copy import deepcopy


def build_metadata(chunk, *, stock_code, report_year):
    result = {
        'chunk_id': chunk['chunk_id'], 'doc_id': chunk['doc_id'],
        'stock_code': stock_code,
        'years': list(chunk['years']), 'page': list(chunk['page']),
        'content_type': chunk['content_type'],
        'main_title': chunk['title']['main_title'],
        'hd2_title': chunk['title']['heading']['text'] if chunk['title']['heading'] else '',
        'data_tags': deepcopy(chunk['data_tags']),
        'table_context': chunk.get('table_context', ''),
        'appendix_id': chunk.get('appendix_id'),
    }
    if all(key in chunk for key in ('main_section', 'sub_section', 'note_title')):
        result.update(main_section=chunk['main_section'], sub_section=chunk['sub_section'],
                      note_title=deepcopy(chunk['note_title']))
    if 'table_completeness' in chunk:
        result['table_completeness'] = chunk['table_completeness']
    if 'directions' in chunk:
        result.update(parent_id=chunk.get('parent_id'), part_index=chunk.get('part_index'),
                      table_year=[r['text'] for r in chunk.get('table_year', [])],
                      directions=[r['text'] for r in chunk['directions']],
                      table_ids=list(chunk.get('table_ids', [])))
    if 'node_type' in chunk:
        result.update(node_type=chunk['node_type'],parent_relation=chunk['parent_relation'],
                      heading_parent_id=chunk['heading_parent_id'])
    return result
