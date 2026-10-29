"""EXPERIMENT_ONLY：分題JSON供重排、Markdown供回答，不包含評分標準或Answer。"""
import json
import re
from Code_2.functions.experiments.evidence_report import EvidenceReportContext


def payloads(paths,result):
    from Code_2.config.embedding import Settings
    context=EvidenceReportContext(Settings(project_root=paths['project_root']))
    output={};used=set();restorer=None
    for number,row in enumerate(result.get('rows',[]),1):
        identity=str(row['ID']);query=row.get('query',{});question=row.get('Question','')
        stem='ID_'+(identity.zfill(3) if re.fullmatch(r'\d+',identity) else f'{number:03d}')
        if stem in used:stem+='_'+str(number)
        used.add(stem)
        candidates=query.get('retrieved_children')
        note=None
        if candidates is None:
            # 舊報告還原僅查來源chunk檔，不讀向量庫、不重新embedding。
            try:
                from Code_2.functions.experiments.child_candidates import ChildCandidates
                if restorer is None:restorer=ChildCandidates(Settings(project_root=paths['project_root']),result)
                candidates,_=restorer.inputs(row,True)
                note='來源舊報告：子項依chunk_id固定順序還原，原排名缺失處為null。'
            except (ValueError,KeyError):
                candidates=query.get('retrieved_evidence',[])
                note='來源缺少可還原子項，保留原候選；candidate_unit=returned，不宣稱為子項。'
        unit='returned' if note and 'candidate_unit=returned' in note else 'child'
        record={'schema_version':'financial-rerank-input/1.0','ID':identity,'Question':question,
                'candidate_unit':unit,'candidate_count':len(candidates),'candidates':candidates,
                'reranked_candidates':query.get('reranked_children') or (query.get('evidence',[]) if query.get('mode')=='rerank' else []),
                'note':note,'status':row.get('status')}
        output[paths['json'].parent/(stem+'.json')]=json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
        selected=query.get('evidence',[])
        selection='來源保存的前10組證據'
        if query.get('mode')=='retrieve' and unit=='child':
            by_id={e['chunk_id']:e for e in query.get('retrieved_evidence',[])}
            selected=[];seen=set()
            chosen=candidates
            selected_ids=query.get('selected_child_ids')
            if selected_ids:
                lookup={c['chunk_id']:c for c in candidates}
                chosen=[lookup[cid] for cid in selected_ids[:10] if cid in lookup]
            elif all(type(c.get('retrieval_rank')) is int for c in candidates):
                chosen=sorted(candidates,key=lambda c:c['retrieval_rank'])
            elif note:
                chosen=[]
                note='舊報告缺少完整原始名次及選取子項，不能猜前10名；請核對總報告已保存的證據。'
            for child in chosen[:10]:
                group=child.get('return_evidence_id') or child.get('parent_id') or child['chunk_id']
                if group in seen:continue
                evidence=by_id.get(group)
                # 可選標題父項不得冒充必回父項。
                if evidence is None or evidence.get('parent_relation')=='heading':
                    evidence=child
                    if child.get('parent_id'):note='缺少完整必回父項，保留子項並明示，不能當作父項完整。'
                selected.append(evidence);seen.add(group)
            selection='先取前10個檢索子項，再帶回必回父項；同父項去重、不補選，原始切法不帶標題父項'
        lines=[f'# ID {identity}',question,'只依以下證據回答；證據不足請列出缺少資料，不推測數值。',
               f'證據選取：{selection}；實際{min(10,len(selected))}組。']
        if note:lines.append(note)
        for evidence in selected[:10]:
            e=context.enrich(evidence)
            lines.extend([f"## [{e.get('id','')}] {e['chunk_id']}",
                          f"來源：{e['doc_id']}｜PDF頁序：{e.get('page',[])}",e['report_text']])
        if not selected:lines.append('無已保存的可用證據。')
        output[paths['json'].parent/(stem+'.md')]=('\n\n'.join(lines)+'\n').encode('utf-8')
    return output
