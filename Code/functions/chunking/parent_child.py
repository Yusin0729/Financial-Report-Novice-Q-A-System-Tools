"""依content/table邊界切塊；內文與跨頁表格強制父項、標題父項另行關聯。"""
import re
from collections import defaultdict
from dataclasses import asdict, replace
from functions.chunking.slicing import slice_atom, remove_heading_marks, split_text
from functions.markdown_processing.mark_headings import _protected_lines
from functions.content_context import add_context

SCHEMA = 'financial-chunks/5.0'
RULE = 'bounded-parent-child/5.7'


def _list_offset(atom):
    lines = atom.content.splitlines(keepends=True)
    protected = _protected_lines(atom.content, lines)
    offset = 0
    for index,line in enumerate(lines):
        if index not in protected and re.match(r'^[ \t]*###(?!#)[ \t]+\S',line):
            return offset
        offset += len(line)
    return None


def logical_blocks(atoms):
    """###前段及後續整組；表格獨立、HD變更停止群組。"""
    result, active = [], None
    for atom in atoms:
        if active is not None and (atom.path != active[0].path or atom.kind == 'table'):
            result.append((active, True))
            active = None
        if atom.kind == 'table':
            result.append(([atom],False))
            continue
        if active is not None:
            active.append(atom)
            continue
        position = _list_offset(atom)
        if position is None:
            result.append(([atom],False))
        else:
            active = []
            if position == 0 and result and not result[-1][1] and result[-1][0][-1].kind == 'text' and result[-1][0][-1].path == atom.path:
                active.extend(result.pop()[0])
            if position and atom.content[:position].strip():
                active.append(slice_atom(atom,0,position))
            active.append(slice_atom(atom,position,len(atom.content)))
    if active is not None:
        result.append((active,True))
    return result


def adjacent_content_blocks(atoms):
    """同一完整HD路徑的相鄰內文先合併；表格及###沿用獨立邊界。"""
    pending, scope = [], None
    for block, is_list in logical_blocks(atoms):
        first = block[0]
        current = (first.main, first.path)
        special = is_list or first.kind == 'table' or first.main == '會計師查核報告'
        if pending and (current != scope or special):
            yield pending, False
            pending = []
        if special:
            yield block, is_list
            scope = None
        else:
            scope = current
            pending.extend(block)
    if pending:
        yield pending, False


def original_blocks(atoms, limit):
    """一般文字跨低層標題累積；達門檻於完整content結束才切，保留hd2邊界。"""
    pending, count, scope = [], 0, None
    for block,is_list in logical_blocks(atoms):
        first=block[0]
        current=(first.main,tuple(p for p in first.path if p[0]<=2))
        special=is_list or first.kind=='table' or first.main=='會計師查核報告'
        if pending and (current!=scope or special):
            yield pending,False
            pending,count=[],0
        if special:
            yield block,is_list
            scope=None
            continue
        scope=current
        pending.extend(block)
        count+=sum(a.weight for a in block)
        if count>=limit:
            yield pending,False
            pending,count=[],0
    if pending:
        yield pending,False


def common_path(atoms):
    path=list(atoms[0].path)
    for atom in atoms[1:]:
        length=0
        for left,right in zip(path,atom.path):
            if left!=right:break
            length+=1
        path=path[:length]
    return path


def _merge(atoms):
    first = atoms[0]
    def records(name):
        values = {r['start']:r for a in atoms for r in getattr(a,name)}
        return tuple(values[k] for k in sorted(values))
    return replace(first,content=''.join(a.content for a in atoms),
                   spans=[s for a in atoms for s in a.spans],
                   pages=sorted({p for a in atoms for p in a.pages}),
                   directions=records('directions'),table_year=records('table_year'))


def _table_parts(atom):
    parts, start, offset, page = [], 0, 0, None
    for span in atom.spans:
        if len(span['pages']) != 1:
            return [atom],False
        number = span['pages'][0]
        if page is not None and page != number:
            parts.append(slice_atom(atom,start,offset))
            start = offset
        page = number
        offset += span['end']-span['start']
    parts.append(slice_atom(atom,start,offset))
    resolved = sorted({p for a in parts for p in a.pages}) == sorted(atom.pages)
    return (parts if resolved else [atom]),resolved


def chunk_parent_child(roots, source, *, identity, source_sha256, config):
    from functions.chunking.hierarchical import make_item
    from functions.chunking.chunks import ChunkResult, validate_chunk_document, render_chunks
    for name in ('recursive_threshold','parent_limit','child_target'):
        if type(getattr(config,name)) is not int or getattr(config,name)<1:
            raise ValueError(f'{name}須為正整數')
    doc_id = f'{identity[0]}{config.document_period}_{identity[1]}_Financial_Report'
    chunks,parents,issues,removed = [],[],[],[]
    groups = defaultdict(list)

    def item(atoms,reason,role='chunk'):
        value = make_item(atoms,identity,doc_id,reason)
        value.update(node_type=role,parent_relation=None,heading_parent_id=None)
        return value

    def parent_for(atoms,reason,role):
        value = item(atoms,reason,role)
        value['chunk_id'] = f'{doc_id}__t{len(parents)+1:05d}'
        parents.append(value)
        return value

    atoms = [atom for root in roots for atom in root.atoms()]
    blocks=original_blocks(atoms,config.recursive_threshold) if config.mode=='original' else adjacent_content_blocks(atoms)
    for raw_atoms,is_list in blocks:
        clean = []
        list_start = next((i for i,a in enumerate(raw_atoms) if _list_offset(a) is not None),None)
        for atom in raw_atoms:
            value,spans = remove_heading_marks(atom)
            clean.append(value)
            removed.extend({**s,'reason':'markdown_heading_marker'} for s in spans)
        first = clean[0]
        reason = 'content_block'
        table = first.kind == 'table'
        if table:
            parts,resolved = _table_parts(first)
            reason = 'table_page' if len(first.pages)>1 else 'standalone_table'
            if not resolved:
                issues.append({'status':'unresolved_table_page_boundary','pages':list(first.pages),
                               'source_start':first.spans[0]['start']})
            pieces = [[a] for a in parts]
        elif first.main == '會計師查核報告':
            pieces = [clean]
            reason = 'audit_heading'
        elif is_list:
            # 已確認例外：編碼群組無論多長均一個Child。
            leading = clean[:list_start] if list_start is not None else []
            trailing = clean[list_start:] if list_start is not None else clean
            pieces = ([leading] if config.mode=='original' else [[a] for a in split_text(_merge(leading),config.recursive_threshold)]) if leading else []
            pieces.append(trailing)
            reason = 'body_list_group'
            if sum(a.weight for a in trailing)>config.recursive_threshold:
                issues.append({'status':'list_group_exceeds_limit_by_design',
                               'characters':sum(a.weight for a in trailing),
                               'limit':config.recursive_threshold,'source_start':trailing[0].spans[0]['start']})
        elif config.mode=='original':
            pieces=[clean]
            reason='content_end_pack'
        else:
            pieces = [[a] for a in split_text(_merge(clean),config.recursive_threshold)]
        parent = None
        if len(pieces)>1 or (table and len(first.pages)>1):
            parent = parent_for(clean,reason,'table_parent' if table else 'content_parent')
        unit_chunks = []
        for number,piece in enumerate(pieces,1):
            child = item(piece,reason)
            child['chunk_id'] = f'{doc_id}__c{len(chunks)+1:05d}'
            if parent:
                child.update(parent_id=parent['chunk_id'],part_index=number,
                             parent_relation='table' if table else 'content')
                if table:
                    child.update(years=list(parent['years']),year_sources=parent['year_sources'],
                                 table_ids=list(parent['table_ids']),table_context=parent['table_context'])
            chunks.append(child)
            unit_chunks.append(child)
        # 忽略Note_Title末層；無可比較前綴則以Sub_Section的真實hd2區間分組。
        path = common_path(clean)
        key = (first.main,tuple(path[:-1] if len(path)>1 else path))
        if config.mode=='parent_child' and path and first.main != '會計師查核報告':
            groups[key].append((clean,unit_chunks,parent))
    for units in groups.values():
        if len(units)<2:
            continue
        all_atoms = [a for values,_,_ in units for a in values]
        parent = parent_for(all_atoms,'heading_group','heading_parent')
        kinds = {a.kind for a in all_atoms}
        if len(kinds)>1:
            parent['content_type']='mixed'
            parent.pop('table_completeness',None)
            parent['table_context']=''
        parent['years'] = sorted({y for _,children,_ in units for child in children for y in child['years']})
        for _,children,mandatory in units:
            for child in children:
                child['heading_parent_id']=parent['chunk_id']
            if mandatory:
                mandatory['heading_parent_id']=parent['chunk_id']
    if not chunks:
        raise ValueError('來源沒有有效正文或表格，未輸出空成功')
    for value in chunks+parents:
        add_context(value, config.table_embedding_mode if value['content_type']=='table' else config.text_embedding_mode)
    doc = {'schema_version':SCHEMA,'rule_version':('content-end-original/1.5' if config.mode=='original' else RULE),'doc_id':doc_id,
           'source_sha256':source_sha256,'excluded_prefix_end':0,
           'chunking':{k:v for k,v in asdict(config).items() if k in
                       ('mode','parent_limit','child_target','recursive_threshold','document_period')},
           'embedding_context_modes':{'text':config.text_embedding_mode,'table':config.table_embedding_mode},
           'chunks':chunks,'parents':parents,'issues':issues,'removed_markup_spans':removed}
    # 來源重建包含所有子項，父項不當作第二份搜尋內容。
    expected = sorted((s['start'],s['end']) for a in atoms for s in a.spans)
    actual = sorted((s['start'],s['end']) for c in chunks for s in c['source_spans'])
    erased = [(s['start'],s['end']) for s in removed]
    def compact(intervals):
        result=[]
        for a,b in sorted(intervals):
            if result and a<result[-1][1]:
                raise ValueError('來源區間重複，拒絕輸出')
            if result and a==result[-1][1]:
                result[-1]=(result[-1][0],b)
            else:
                result.append((a,b))
        return result
    if compact(expected)!=compact(actual+erased):
        raise ValueError('來源遺失或額外加入內容，未輸出部分結果')
    from functions.content_context import content_body
    for value in chunks+parents:
        if ''.join(source[s['start']:s['end']] for s in value['source_spans'])!=content_body(value):
            raise ValueError('chunk正文無法由來源位置重建')
    from functions.chunking.blank_lines import remove_blank_lines
    remove_blank_lines(doc, source)
    validate_chunk_document(doc)
    return ChunkResult(doc,render_chunks(doc,{}),0)
