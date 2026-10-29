"""純記憶體前處理，不寫Output、不載入模型或PDF環境套件。"""
import re
from copy import deepcopy
from Code.config.embedding import CHUNK_SCHEMA, PREPARED_SCHEMA, PREPARE_RULE
from Code.functions.embedding.metadata import build_metadata
from Code.functions.embedding.table_text import convert_content
from Code.functions.embedding.sections import section_fields
from Code.functions.content_context import content_body, validate_context_modes, SCHEMA as CONTEXT_SCHEMA
from Code.functions.parent_relations import SCHEMA as HIERARCHY_SCHEMA, validate_relations, contains


def validate_document(doc):
    if not isinstance(doc, dict) or doc.get('schema_version') not in (
            CHUNK_SCHEMA, 'financial-chunks/1.0', 'financial-chunks/3.0', 'financial-chunks/3.1', 'financial-chunks/4.0', CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
        raise ValueError('來源不是支援的financial-chunks/1.0至5.0格式')
    identity = re.fullmatch(r'(\d{4})(Q[1-4])_(\d+)_Financial_Report', doc.get('doc_id', ''))
    if not identity or not re.fullmatch(r'[a-f0-9]{64}', doc.get('source_sha256', '')):
        raise ValueError('文件識別或來源雜湊無效')
    if not isinstance(doc.get('chunks'), list) or not doc['chunks']:
        raise ValueError('沒有有效chunks')
    validate_context_modes(doc)
    year, _, stock = identity.groups()
    seen = set()
    if doc['schema_version'] in ('financial-chunks/4.0', CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
        spec = doc.get('chunking')
        if (not isinstance(spec, dict) or set(spec) != {'mode','parent_limit','child_target','recursive_threshold','document_period'}
                or spec['mode'] not in ('original','parent_child')
                or any(type(spec[k]) is not int or spec[k] < 1 for k in ('parent_limit','child_target','recursive_threshold'))
                or (doc['schema_version']!=HIERARCHY_SCHEMA and spec['mode']=='original' and spec['child_target'] > spec['parent_limit']) or spec['document_period'] != identity[2]):
            raise ValueError('4.0缺少有效切塊模式／參數，不能混用索引')

    def heading(node, level=1):
        if not isinstance(node, dict) or type(node.get('level')) is not int or node['level'] <= level:
            raise ValueError('標題層級無效')
        if not isinstance(node.get('text'), str) or not node['text'].strip() or not isinstance(node.get('children'), list):
            raise ValueError('標題樹內容無效')
        for child in node['children']:
            heading(child, node['level'])

    parents = doc.get('parents', [])
    if not isinstance(parents, list):
        raise ValueError('parents不是清單')
    parent_map = {p['chunk_id']: p for p in parents}
    if len(parent_map) != len(parents):
        raise ValueError('父表識別碼重複')
    for c in doc['chunks'] + parents:
        if not isinstance(c, dict):
            raise ValueError('chunk不是物件')
        cid = c.get('chunk_id')
        if not isinstance(cid, str) or not re.fullmatch(re.escape(doc['doc_id']) + r'__[ct]\d{5,}', cid) or cid in seen:
            raise ValueError('chunk_id無效或重複')
        seen.add(cid)
        mixed = doc['schema_version']==HIERARCHY_SCHEMA and c.get('node_type')=='heading_parent' and c.get('content_type')=='mixed'
        if c.get('doc_id') != doc['doc_id'] or (c.get('content_type') not in ('text', 'table') and not mixed):
            raise ValueError('chunk文件錯配或類型無效')
        if not isinstance(c.get('content'), str) or not c['content'].strip():
            raise ValueError('chunk內容空白')
        if doc['schema_version'] in (CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
            if 'content_prefix' not in c or not content_body(c).strip():
                raise ValueError('4.1缺少有效content首行或正文')
        elif 'content_prefix' in c:
            raise ValueError('舊版schema不可混入新版content首行')
        if 'table_completeness' in c:
            value = c['table_completeness']
            expected = 0 if '<cannotfindtable>' in c['content'] else 1
            if c['content_type'] != 'table' or type(value) is not int or value != expected:
                raise ValueError('table_completeness須與表格標記相符，使用整數0或1')
        years = c.get('years')
        if (not isinstance(years, list) or not years or
                any(type(v) is not int or not 1900 <= v <= 2199 for v in years) or years != sorted(set(years))):
            raise ValueError('years須為不重複、排序的西元整數年份清單')
        if c['content_type'] == 'text' and years != [int(year)]:
            raise ValueError('純文字年份須為文件年度')
        if c.get('parent_id') is not None:
            parent = parent_map.get(c['parent_id'])
            if (parent is None or type(c.get('part_index')) is not int or c['part_index'] < 1 or
                    not contains(parent,c)):
                raise ValueError('子塊與完整父表錯配')
        pages = c.get('page')
        if not isinstance(pages, list) or not pages or any(type(p) is not int or p < 1 for p in pages):
            raise ValueError('page必須為正整數清單')
        if pages != sorted(set(pages)):
            raise ValueError('page必須排序且不重複')
        title = c.get('title')
        if (not isinstance(title, dict) or not isinstance(title.get('main_title'), str)
                or 'heading' not in title):
            raise ValueError('缺少title')
        root = title.get('heading')
        if root is None:
            if doc['schema_version'] not in ('financial-chunks/3.0', 'financial-chunks/3.1', 'financial-chunks/4.0', CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
                raise ValueError('舊版chunk缺少標題樹')
        else:
            heading(root)
        if (root is not None and root['level'] != 2) or c.get('data_tags') != []:
            raise ValueError('缺少hd2或非目前支援的data_tags')
        if doc['schema_version'] in ('financial-chunks/3.1', 'financial-chunks/4.0', CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
            if any(c.get(key) != value for key, value in section_fields(title).items()):
                raise ValueError('3.1章節欄位缺失或與標題階層不符')
        if doc['schema_version'] in ('financial-chunks/4.0', CONTEXT_SCHEMA,HIERARCHY_SCHEMA):
            if (not isinstance(c.get('table_ids'), list)
                    or any(not isinstance(value, str) or not value for value in c['table_ids'])
                    or len(set(c['table_ids'])) != len(c['table_ids'])):
                raise ValueError('4.0表格識別清單無效或重複')
            for name in ('directions', 'table_year'):
                if not isinstance(c.get(name), list) or any(not isinstance(r, dict)
                    or not isinstance(r.get('text'), str) or r.get('kind') not in
                    ('table_year','table_direction','content_direction') for r in c[name]):
                    raise ValueError('4.0說明／年度metadata格式無效')
        if not isinstance(c.get('source_spans'), list) or not c['source_spans']:
            raise ValueError('缺少來源位置')
        for span in c['source_spans']:
            if (not isinstance(span, dict) or type(span.get('start')) is not int or
                    type(span.get('end')) is not int or not 0 <= span['start'] < span['end'] or
                    not isinstance(span.get('pages'), list) or not span['pages'] or
                    any(type(p) is not int or p < 1 for p in span['pages'])):
                raise ValueError('來源位置格式無效')
        markers = list(re.finditer(r'<!--\s*Page:\s*(\d+)_(\d{4})_P(\d+)\s*-->', c['content']))
        for i, match in enumerate(markers):
            s, y, p = match.groups()
            if (s, y) != (stock, year):
                raise ValueError('正文Page與metadata不符')
            if int(p) not in pages:
                # 舊chunk可含相鄰頁的純空白邊界；不把這些頁冒充正文頁序。
                end = markers[i + 1].start() if i + 1 < len(markers) else len(c['content'])
                segment = re.sub(r'<!--.*?-->|<[^>]*>', '', c['content'][match.end():end], flags=re.S)
                if segment.strip():
                    raise ValueError(f'{cid}：非空正文Page {p} 不在metadata頁序 {pages} 內')
    if doc['schema_version']==HIERARCHY_SCHEMA:
        validate_relations(doc)
    return int(year), stock


def title_context(title):
    """章節索引清楚標為整塊涵蓋範圍，不把多個子節誤標成單一路徑。"""
    root = title['heading']
    parts = [v for v in (title['main_title'], root['text'] if root else '') if v.strip()]
    paths = []

    def visit(node, ancestors):
        path = ancestors + [node['text']]
        if not node['children']:
            paths.append(' > '.join(path))
        for child in node['children']:
            visit(child, path)
    for child in root['children'] if root else []:
        visit(child, [])
    if paths:
        parts.append('本塊小節索引：\n' + '\n'.join(paths))
    return '\n'.join(parts)


def embedding_context(chunk):
    """舊版補脈絡；新版content已有首行，不重複加入標題及說明。"""
    if 'content_prefix' in chunk:
        content_body(chunk)  # 驗證生成首行，損壞時停止，不默默降級。
        return ''
    parts = [title_context(chunk['title'])]
    seen = set()
    for record in chunk.get('directions', []):
        text = record['text']
        if text and text not in seen:
            parts.append('說明：' + text)
            seen.add(text)
    context = chunk.get('table_context', '')
    if context and context not in seen:
        parts.append('表格前置標題：' + context)
    return '\n'.join(p for p in parts if p.strip())


def prepare_document(doc, *, input_sha256, embedding_context_modes=None):
    if not isinstance(input_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', input_sha256):
        raise ValueError('輸入chunk JSON雜湊無效')
    year, stock = validate_document(doc)
    if 'embedding_context_modes' in doc:
        if embedding_context_modes is not None and embedding_context_modes != doc['embedding_context_modes']:
            raise ValueError('不可在建庫時覆寫第四階段的embedding脈絡設定')
        embedding_context_modes = doc['embedding_context_modes']
    if embedding_context_modes is not None:
        from Code.functions.embedding.context_modes import validate_modes
        embedding_context_modes = validate_modes(embedding_context_modes)
    result = {'schema_version': PREPARED_SCHEMA, 'rule_version': PREPARE_RULE,
              'source_chunk_schema': doc['schema_version'], 'source_rule_version': doc.get('rule_version'),
              'doc_id': doc['doc_id'], 'input_sha256': input_sha256,
              'source_sha256': doc['source_sha256'], 'token_check_status': 'pending_model_selection',
              'model': None, 'chunks': [], 'parents': deepcopy(doc.get('parents', []))}
    if 'chunking' in doc:
        result['chunking'] = deepcopy(doc['chunking'])
    if embedding_context_modes is not None:
        result['embedding_context_modes'] = embedding_context_modes
    for chunk in doc['chunks']:
        body, tables = convert_content(chunk['content'])
        candidate = '<cannotfindtable>' in chunk['content']
        pipe = bool(re.search(r'(?m)^\s*\|.*\|\s*\n\s*\|[ :|\-]+\|', chunk['content']))
        if not body.strip() or (chunk['content_type'] == 'table') != bool(tables or candidate or pipe):
            raise ValueError(f'{chunk["chunk_id"]}：內容類型與HTML表格不符或空白')
        context = embedding_context(chunk)
        text = context + '\n\n' + body if context else body
        if embedding_context_modes is not None:
            from Code.functions.embedding.context_modes import embedding_text
            text = embedding_text(chunk, embedding_context_modes[chunk['content_type']])
        result['chunks'].append({
            'chunk_id': chunk['chunk_id'], 'embedding_text': text,
            'metadata': build_metadata(chunk, stock_code=stock, report_year=year),
            'original_chunk': deepcopy(chunk),
            'preparation': {'html_table_count': len(tables), 'original_characters': len(chunk['content']),
                            'embedding_characters': len(text), 'token_count': None,
                            'token_check_status': 'pending_model_selection'},
        })
    return result


def render_prepared(doc):
    parts = ['# Embedding 前處理檢查', '尚未計算向量；tokens 待選定模型後檢查。']
    for c in doc['chunks']:
        parts.extend(['---', f'## {c["chunk_id"]}',
                      f'PDF 頁序：{", ".join(map(str, c["metadata"]["page"]))}', c['embedding_text']])
    return '\n\n'.join(parts) + '\n'
