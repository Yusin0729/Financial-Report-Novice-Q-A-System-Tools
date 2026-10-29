"""EXPERIMENT_ONLY：來源評分，不參與向量檢索、重排序或回答提示詞。"""
import re
import unicodedata
from Code_2.config.evaluation import EvaluationSettings

TITLE_RULE='year-title-dual/3.2'
NUMERIC_RULE='numbers-only/1.0'
SUPPORTED_RULES=('year-title-dual/2.0','year-title-dual/3.0','year-title-dual/3.1',TITLE_RULE,
                 'year-title-numbers/1.0','year-title-numbers/1.1','year-title-numbers/1.2',NUMERIC_RULE)


def normalized(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value)))

def doc_identity(value):
    match=re.fullmatch(r'(\d{4})(?:Q[1-4]|0[1-4])?_(\d+)_.+',str(value),re.I)
    return (int(match[1]),match[2]) if match else None

def title_name(value):
    """只忽略各層開頭編號；保留IFRS、數字指標等標題語意，不做模糊關鍵字命中。"""
    parts=[]
    for part in str(value).split('>'):
        text=unicodedata.normalize('NFKC',part).strip()
        text=re.sub(r'^(?:\(\s*[一二三四五六七八九十百千〇零兩廿卅壹貳參肆伍陸柒捌玖拾0-9]+\s*\)\s*[、.．]?|[一二三四五六七八九十百千〇零兩廿卅壹貳參肆伍陸柒捌玖拾0-9]+\s*[、.．])\s*','',text)
        if text:parts.append(normalized(text))
    return '>'.join(parts)


def title_keys(value):
    name=title_name(value)
    return set(name.split('>'))|{name} if name else set()


def document_matches(row,chunk):
    # Doc_Id僅用股號；不再限制來源財報年度。
    expected=doc_identity(row.get('Doc_Id',''))
    stock=row.get('stock_code') or (expected[1] if expected else None)
    actual=doc_identity(chunk.get('doc_id'))
    return stock is None or (actual is not None and stock==actual[1])

def eligible(row,chunk):
    return document_matches(row,chunk) and (not row.get('filter_years') or bool(set(row['filter_years']) & set(chunk.get('years',[]))))

def page_matches(expected,chunk):
    identity=doc_identity(chunk.get('doc_id'))
    return (expected['page'] in chunk.get('page',[]) and
            (expected['report_year'] is None or (identity and expected['report_year']==identity[0])) and
            (expected['stock_code'] is None or (identity and expected['stock_code']==identity[1])))

def page_label(page):
    return f"{page['report_year']}_{page['stock_code']}_P{page['page']}" if page['report_year'] else f"P{page['page']}"

def effective_candidates(candidates,limit=None,*,include_members=False):
    """必回父項代表同一群組，只留第一筆；未命中群組也保留有效排名位置。"""
    cfg=EvaluationSettings();result=[];seen={}
    for original_rank,candidate in enumerate(candidates,1):
        chunk=candidate['chunk']
        group=chunk.get('parent_id') or chunk['chunk_id']
        key=(chunk['doc_id'],group)
        member={**candidate,'original_rank':candidate.get('rank',original_rank)}
        if key in seen:
            if include_members:seen[key]['numeric_members'].append(member)
            continue
        if len(result)>=(limit or cfg.top_k):continue
        entry={**candidate,'original_rank':candidate.get('rank',original_rank),
               'effective_rank':len(result)+1,'group_id':group}
        if include_members:entry['numeric_members']=[member]
        seen[key]=entry;result.append(entry)
    return result

def score(row,candidates,*,retrieve_k=None):
    cfg=EvaluationSettings()
    retrieve_k=cfg.top_k if retrieve_k is None else retrieve_k
    if type(retrieve_k) is not int or retrieve_k<1:
        raise ValueError('評分召回數須為正整數')
    expected_pages=row.get('expected_pages',[]);expected_titles=row.get('expected_titles',[])
    targets=[{'year':year,'title':title,'label':f'{year}｜{title}' if year is not None else title}
             for title in expected_titles for year in (row.get('filter_years') or [None])]
    share=cfg.total_score/len(targets) if targets else 0.0
    penalty=share/retrieve_k
    # EXPERIMENT_ONLY：只對已明確標註的年度×標題套用必要數字，不從Answer猜。
    from Code_2.functions.experiments.numeric_evidence import parse_targets,target_numbers,missing_numbers
    definition=row.get('numeric_targets')
    numeric_targets=parse_targets(row.get('Required_Numbers') if definition is None else definition)
    # 年度、標題只作標準分組識別，不再限制數字來源的metadata。
    if numeric_targets is not None:
        targets=[{'year':t['year'],'title':t['title'],
                  'label':f"{t['year']}｜{t['title']}" if t['year'] is not None else t['title']}
                 for t in numeric_targets]
        share=cfg.total_score/len(targets)
        penalty=share/retrieve_k
    entries=effective_candidates(candidates,limit=retrieve_k,include_members=numeric_targets is not None)
    review_pending=row.get('Required_Numbers_Status')=='pending'
    missing_definitions=[]
    if numeric_targets is not None:
        expected={(t['year'],title_name(t['title'])) for t in targets}
        if any((t['year'],title_name(t['title'])) not in expected for t in numeric_targets):
            raise ValueError('Required_Numbers包含不屬於本題年度×標題的項目')
        missing_definitions=[t['label'] for t in targets if target_numbers(numeric_targets,t['year'],t['title']) is None]
    page_hits={};title_hits={};target_hits={};details=[];number_hits={t['label']:{} for t in targets}
    for entry in entries:
        chunk=entry['chunk'];valid=eligible(row,chunk)
        matched_pages=[page_label(p) for p in expected_pages if valid and page_matches(p,chunk)]
        for name in matched_pages:page_hits.setdefault(name,entry['effective_rank'])
        # 目標可比對小標或標題路徑各層名稱；頁碼不作得分門檻。
        names=set().union(*(title_keys(t) for t in chunk.get('note_title',[])))
        if chunk.get('sub_section'):
            names.update(title_keys(chunk['sub_section']))
        matched_titles=[name for name in expected_titles if valid and bool(title_name(name)) and title_name(name) in names]
        for name in matched_titles:title_hits.setdefault(name,entry['effective_rank'])
        matched_targets=[t['label'] for t in targets if t['title'] in matched_titles and
                         (t['year'] is None or t['year'] in chunk.get('years',[]))]
        numeric_checks=[]
        if numeric_targets is not None:
            allowed=[]
            for target in targets:
                required=target_numbers(numeric_targets,target['year'],target['title'])
                found_here=[];qualified=False
                for member in entry['numeric_members']:
                    mc=member['chunk']
                    qualified=True
                    if required:
                        missing=missing_numbers(required,member.get('text',''))
                        for number in required:
                            if number in missing:continue
                            if number not in found_here:found_here.append(number)
                            number_hits[target['label']].setdefault(number,{
                                'chunk_id':mc['chunk_id'],'doc_id':mc['doc_id'],
                                'effective_rank':entry['effective_rank'],'original_rank':member['original_rank']})
                if not qualified:continue
                missing=[n for n in required if n not in found_here] if required else None
                remaining=[n for n in required if n not in number_hits[target['label']]] if required else None
                completed_here=remaining==[] and target['label'] not in target_hits
                numeric_checks.append({'target':target['label'],'required_numbers':required,
                                       'found_numbers':found_here,'missing_numbers':missing,
                                       'cumulative_missing_numbers':remaining,'matched':completed_here,
                                       'completed_here':completed_here})
                if completed_here:allowed.append(target['label'])
            matched_targets=allowed
        for name in matched_targets:target_hits.setdefault(name,entry['effective_rank'])
        details.append({'chunk_id':chunk['chunk_id'],'matched_chunk_ids':entry.get('matched_chunk_ids',[chunk['chunk_id']]),
            'doc_id':chunk['doc_id'],'years':chunk.get('years',[]),'page':chunk.get('page',[]),
            'sub_section':chunk.get('sub_section',''),'note_title':chunk.get('note_title',[]),'effective_rank':entry['effective_rank'],
            'original_rank':entry['original_rank'],'group_id':entry['group_id'],
            'eligible':valid,'matched_pages':matched_pages,'matched_titles':matched_titles,'matched_targets':matched_targets,
            'parent_relation':entry.get('parent_relation'), 'text':entry.get('text',''),
            'numeric_member_ids':[m['chunk']['chunk_id'] for m in entry.get('numeric_members',[])]})
    # 年度×標題各占10/N；同一項只採第一個有效排名。
    contributions=[];raw_total=None
    if targets:
        labels=[t['label'] for t in targets]
        ordered=sorted(target_hits.items(),key=lambda item:(item[1],labels.index(item[0])))
        for ideal,(name,rank) in enumerate(ordered,1):
            points=max(0.0,share-penalty*max(0,rank-ideal))
            target=targets[labels.index(name)]
            contributions.append({'target':name,'title':target['title'],'year':target['year'],
                'rank':rank,'ideal_rank':ideal,'raw_score':share,'score':points,'rank_penalty':penalty})
        total=round(min(cfg.total_score,sum(c['score'] for c in contributions)),4)
        raw_total=round(cfg.total_score*len(target_hits)/len(targets),4)
    else:total=None
    if missing_definitions or review_pending:
        total=raw_total=None
        contributions=[]
    missing_pages=[page_label(p) for p in expected_pages if page_label(p) not in page_hits]
    missing_titles=[t for t in expected_titles if t not in title_hits]
    return {'score':total,'weighted_score':total,'raw_score':raw_total,
        'targets':targets,'target_hits':target_hits,'target_coverage':f'{len(target_hits)}/{len(targets)}',
        'missing_targets':[t['label'] for t in targets if t['label'] not in target_hits],'page_coverage':f'{len(page_hits)}/{len(expected_pages)}',
        'title_coverage':f'{len(title_hits)}/{len(expected_titles)}','page_hits':page_hits,'title_hits':title_hits,
        'missing_pages':missing_pages,'missing_titles':missing_titles,'contributions':contributions,'top20':details,
        'retrieve_k':retrieve_k,'rank_penalty':penalty,'evaluated_count':len(entries),
        'complete':bool(targets and not missing_definitions and not review_pending and len(target_hits)==len(targets)),
        'page_is_reference_only':True,'title_matching':'ignore-leading-number/full-heading',
        'scoring_rule':NUMERIC_RULE if numeric_targets is not None or review_pending else TITLE_RULE,
        'rank_weighting':'per-target-share','rank_decay_fraction':1/retrieve_k,
        'numeric_targets':numeric_targets,'missing_number_definitions':missing_definitions,
        'numeric_aggregation':'all-chunks-union' if numeric_targets is not None else None,'number_hits':number_hits,
        'numeric_metadata_gate':False if numeric_targets is not None else None,
        'numeric_completion_rank':'last-required-number-first-effective-rank',
        'numeric_review_status':row.get('Required_Numbers_Status'),
        'scoring_note':('必要數字待確認：'+row.get('Required_Numbers_Note','')) if review_pending else
                       (('必要數字標準未補齊：'+'；'.join(missing_definitions)) if missing_definitions else
                       (None if total is not None else '缺少Evidence_Note_Title，無法計分'))}
