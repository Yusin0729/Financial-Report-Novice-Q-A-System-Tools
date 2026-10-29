"""共用父子契約；由Code建庫與Code_2召回使用，不依賴同名頂層config。"""
from .content_context import content_body
import re
from html import unescape

SCHEMA = 'financial-chunks/5.0'
LINKS = (('parent_id','original_parent'),('heading_parent_id','original_heading_parent'))


def contains(parent,child):
    if parent.get('doc_id')!=child.get('doc_id') or content_body(child) not in content_body(parent):
        return False
    if not set(child.get('page',[])).issubset(parent.get('page',[])):
        return False
    if child.get('node_type') is not None:
        return all(any(p['start']<=s['start'] and s['end']<=p['end'] for p in parent['source_spans'])
                   for s in child['source_spans'])
    return True


def validate_relations(doc):
    spec=doc.get('chunking',{})
    if (spec.get('mode') not in ('original','parent_child') or
            (spec.get('mode')=='original' and not str(doc.get('rule_version','')).startswith('content-end-original/')) or type(spec.get('recursive_threshold')) is not int or spec['recursive_threshold']<1):
        raise ValueError('新版父子資料缺少有效模式或內文字數上限')
    parents={p['chunk_id']:p for p in doc.get('parents',[])}
    search_ids={c['chunk_id'] for c in doc['chunks']}
    for child in doc['chunks']+list(parents.values()):
        if not {'node_type','parent_relation','heading_parent_id','content_prefix'}.issubset(child):
            raise ValueError('新版父子關係欄位缺少')
        body=content_body(child)
        visible=unescape(re.sub(r'<[^>]*>|<!--.*?-->','',body,flags=re.S))
        visible=re.sub(r'(?m)^[ \t]*#{1,6}[ \t]*','',visible)
        if child.get('body_char_count')!=sum(not c.isspace() for c in visible):
            raise ValueError('正文字數與content首行後的來源正文不符')
        if sum(s['end']-s['start'] for s in child['source_spans'])!=len(body):
            raise ValueError('來源字元長度與正文不符')
        role=child.get('node_type')
        if role not in ('chunk','content_parent','table_parent','heading_parent'):
            raise ValueError('未知父子節點類型')
        if (child['chunk_id'] in search_ids) != (role=='chunk'):
            raise ValueError('搜尋節點與非向量父項混用')
        for field,_ in LINKS:
            parent_id=child.get(field)
            if parent_id is not None:
                parent=parents.get(parent_id)
                relation=child.get('parent_relation')
                if field=='parent_id' and relation not in ('content','table'):
                    raise ValueError('未知強制父項關係')
                expected='heading_parent' if field=='heading_parent_id' else relation+'_parent'
                if parent is None or parent.get('node_type')!=expected or not contains(parent,child):
                    raise ValueError('父項類型、來源範圍或正文錯配')
                if field=='parent_id' and parent.get('heading_parent_id')!=child.get('heading_parent_id'):
                    raise ValueError('強制父項與子項所屬標題群組不一致')
        if child.get('parent_id') is None:
            if child.get('parent_relation') is not None or child.get('part_index') is not None:
                raise ValueError('無強制父項卻有父子類型或順序')
        elif role!='chunk' or child.get('parent_relation') not in ('content','table'):
            raise ValueError('強制父項關係無效')
        if role=='heading_parent' and child.get('heading_parent_id') is not None:
            raise ValueError('標題父項不可形成循環或額外遞迴')
    for parent_id,parent in parents.items():
        heading=parent['node_type']=='heading_parent'
        field='heading_parent_id' if heading else 'parent_id'
        children=[c for c in doc['chunks'] if c.get(field)==parent_id]
        if not children:
            raise ValueError('父項沒有對應搜尋子項')
        if not heading:
            children.sort(key=lambda c:c['part_index'])
            if [c['part_index'] for c in children]!=list(range(1,len(children)+1)):
                raise ValueError('強制父項子項順序不完整')
        else:
            children.sort(key=lambda c:c['source_spans'][0]['start'])
        if (''.join(content_body(c) for c in children)!=content_body(parent) or
                sorted({p for c in children for p in c['page']})!=parent['page']):
            raise ValueError('父項與完整子項正文或頁序不一致')
