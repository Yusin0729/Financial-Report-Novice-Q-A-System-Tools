"""EXPERIMENT_ONLY：已保存評分的九頁作圖表；不查索引、不呼叫模型。

移除時取消eval_run.excel_report及web.comparison的呼叫；正式問答不依賴本模組。
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from statistics import mean

NAMES=('作圖說明','檢索方法與題型','檢索TopK曲線','檢索五筆增量','檢索逐題對照',
       '重排前後比較','重排TopK曲線','重排逐題差異','重排成本效益')
BAD={'failed','not_run','corpus_unavailable'}
KINDS=('整體','表格','文字','混用','未標註')
BASE=['比較群','方法','模型','切法','文字標籤','表格標籤','評分版本','來源']


def avg(values):
    values=[v for v in values if v is not None]
    return round(mean(values),4) if values else None


def category(row):
    return {'table':'表格','text':'文字','mixed':'混用'}.get(
        row.get('reference',{}).get('Evidence_Type'),'未標註')


def valid(row,s):
    return row.get('status') not in BAD and isinstance(s,dict) and s.get('raw_score') is not None and s.get('score') is not None


def prefix(s,k):
    """沿用來源貢獻及有效名次；不在每個K改扣分率。"""
    parts=[c for c in s.get('contributions',[]) if c['rank']<=k]
    raw=round(sum(c['raw_score'] for c in parts),4)
    weighted=round(sum(c['score'] for c in parts),4)
    return raw,weighted,raw>=9.9999


def info(result,source):
    index=result.get('index',{});signature=index.get('signature',{})
    settings=result.get('settings',{});cut=signature.get('chunking',{})
    modes=signature.get('embedding_context_modes',{})
    labels={'body':'純正文','description':'說明','full':'完整'}
    mode=cut.get('mode');limit=cut.get('recursive_threshold')
    cut_name='原始' if mode=='original' else (f'父子{limit}' if mode=='parent_child' and limit else '未知')
    name=index.get('display_name') or signature.get('experiment',{}).get('name') or index.get('collection') or '未知方法'
    profile=signature.get('model',{})
    model=profile.get('model') or index.get('backend') or settings.get('backend') or '未知'
    group=re.search(r'\bG[1-9]\b',name)
    if group:name=group[0]
    if settings.get('mode') == 'rerank':
        rerank_model = settings.get('rerank_model') or next((r.get('query',{}).get('rerank_model') for r in result.get('rows',[]) if r.get('query',{}).get('rerank_model')), '未知重排模型')
        name += ' / ' + rerank_model
    # 題庫、模型、K、標題父項設定相異時分群；不同評分版本另外分群。
    standards=[{k:r.get('reference',{}).get(k) for k in
                ('ID','Question','numeric_targets','Required_Numbers','Required_Numbers_Status','Years','Doc_Id','expected_titles')}
               | {'ID':r.get('ID'),'Question':r.get('Question')} for r in result.get('rows',[])]
    standards.sort(key=lambda r:str(r['ID']))
    key=[standards,profile or model,settings.get('retrieve_k'),settings.get('include_heading_parent',False)]
    digest=hashlib.sha256(json.dumps(key,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:10]
    return [digest,name,model,cut_name,labels.get(modes.get('text'),'未知'),
            labels.get(modes.get('table'),'未知'),result.get('scoring_rule','未知'),source]


def _stage_meta(base,s):
    output=list(base);output[6]=s.get('scoring_rule') or base[6]
    output[0]=base[0]+'/'+output[6]
    return output


def _state(raw):
    return '不計分' if raw is None else ('成功' if raw>=9.9999 else ('部分命中' if raw>0 else '未命中'))


def build_tables(results):
    """results為[(來源名稱,完整批次結果)]，單／多方法使用同一輸出契約。"""
    tables={name:[] for name in NAMES}
    tables[NAMES[0]]=[['資料表','建議圖型','主要表達','橫軸／分組','縱軸／數值','解讀與限制'],
        [NAMES[1],'九宮格熱圖／分組長條圖','九種標籤在250、700、原始對題型的影響','切法、文字標籤、表格標籤、題型','原始與加權平均分數，分開作圖','只比較相同比較群；混用另列；整體每題一次；單方法報告不代表已完成27組'],
        [NAMES[2],'折線圖','召回幾組才找齊、正確證據是否更早出現','有效Top K；方法、題型、階段','原始／加權平均、完全命中率','K為同必回父項去重後名次，不等於原始子項筆數；扣分分母固定來源召回上限'],
        [NAMES[3],'增量長條圖','哪段提升最多、何時趨平','每5個有效名次為一區塊','原始增分、加權增分、完全命中率增量','增量為0只代表截至當次召回無新增；不自動宣稱最佳K'],
        [NAMES[4],'逐題熱圖','錯題是否相同、哪些題普遍困難','方法×題號','分數／成功狀態','成功＝必要證據原始分數10；不是LLM答案正確率；不計分不得當失敗'],
        [NAMES[5],'分組長條圖','重排是否改善、哪種方法較好','方法、題型、評估單位','前後Top10原始／加權平均及差值','只以同版本同題配對；不拿檢索Top50與重排Top10直接比較'],
        [NAMES[6],'折線圖','保留幾組證據、是否提早命中','有效Top1～10、前後階段','原始／加權平均與完全命中率','未保存子項重排評分者不得假稱子項曲線；只報已有階段'],
        [NAMES[7],'差異熱圖','哪些題改善、退步、沒有改變','方法×題號','原始差、加權差、成功變化','改善及退步分兩種分數；來源版本不同則不計差'],
        [NAMES[8],'成本效益散點圖','提升是否值得時間與token','重排序秒數／實際API tokens','原始／加權分數提升','token不等於費用；未記錄用量留白；來源檢索耗時不算成本次重排耗時'],
        ['共同規則','','不重新檢索、重排或生成答案','','','圖表資料不含chunk全文／Answer；完整資料仍在result.json。跨方法平均只使用相同群內共同可評題，另列原可評及未納入題數。'],
        ['題型','','表格、文字、混用分開；整體含全部','','','類型由題庫Evidence_Type提供，不從命中chunk反推，避免倖存者偏差。跨頁欄保留人工標記，unknown不當成否。'],
        ['階段代碼','','retrieval＝檢索子項；returned＝召回父項後；rerank＝重排序','','','前兩者分開呈現。舊報告沒有保存子項重排評分時，重排曲線只呈現已保存的證據／父項階段，不假造子項結果。'],
        ['缺資料','','沒有重排序資料的表僅保留欄名','','','不填0冒充未執行結果；同群不同方法若不是同一題集會分群。']]
    tables[NAMES[1]]=[BASE+['階段','題型','共同計分題數','本方法原可評題數','未納入題數','原始平均','加權平均','完全命中題數','完全命中率']]
    tables[NAMES[2]]=[BASE+['階段','題型','有效TopK','計分題數','原始平均','加權平均','完全命中題數','完全命中率']]
    tables[NAMES[3]]=[BASE+['階段','題型','區塊起點','區塊終點','計分題數','原始增分','加權增分','完全命中率增量']]
    tables[NAMES[4]]=[BASE+['階段','ID','題目','題型','跨頁表格','執行狀態','原始分數','加權分數','成功狀態','目標覆蓋','缺少目標','首次完整有效名次','耗時秒','共同計分題','Top20 chunk_id']]
    tables[NAMES[5]]=[BASE+['評估單位','題型','有效TopK','配對題數','檢索原始平均','重排原始平均','原始提升','檢索加權平均','重排加權平均','加權提升','檢索完全命中率','重排完全命中率']]
    tables[NAMES[6]]=[BASE+['評估單位','題型','有效TopK','配對題數','檢索原始平均','重排原始平均','檢索加權平均','重排加權平均','檢索完全命中率','重排完全命中率']]
    tables[NAMES[7]]=[BASE+['ID','題目','題型','跨頁表格','有效TopK','檢索原始','重排原始','原始差','檢索加權','重排加權','加權差','原始變化','加權變化','成功變化','配對說明']]
    tables[NAMES[8]]=[BASE+['題型','有效TopK','配對題數','原始提升','加權提升','平均重排秒數','有耗時紀錄題數','重排API tokens總數','有用量紀錄題數','原始每千token提升','加權每千token提升']]
    records=[]
    for source,result in results:
        if result.get('schema_version')!='financial-evaluation/1.0':raise ValueError('作圖表僅接受完整Excel批次結果')
        base=info(result,source);rows=result.get('rows',[])
        k=result.get('settings',{}).get('retrieve_k')
        if type(k) is not int or k<1:raise ValueError('來源召回上限無效')
        if len({r['ID'] for r in rows})!=len(rows):raise ValueError('來源題號重複')
        for stage in ('retrieval','returned'):
            sample=next((r.get('scores',{}).get(stage) for r in rows if r.get('scores',{}).get(stage)),None)
            if sample is not None:records.append((result,base,stage,_stage_meta(base,sample),k))
    # 群內相同題集的共同可評ID，避免只在單一方法成功的題造成平均偏差。
    common={}
    for result,base,stage,meta,k in records:
        key=(meta[0],stage)
        ids={r['ID'] for r in result['rows'] if valid(r,r.get('scores',{}).get(stage))}
        common[key]=ids if key not in common else common[key]&ids
    for result,base,stage,meta,k in records:
        included=common[(meta[0],stage)]
        scored=[r for r in result['rows'] if r['ID'] in included]
        for r in result['rows']:
            s=r.get('scores',{}).get(stage,{})
            raw=s.get('raw_score') if valid(r,s) else None
            full_rank=max(s.get('target_hits',{}).values(),default=None) if raw is not None and raw>=9.9999 else None
            ids='；'.join(c['chunk_id'] for c in s.get('top20',[])[:20])
            tables[NAMES[4]].append(meta+[{'retrieval':'檢索子項','returned':'召回父項後'}[stage],r['ID'],r.get('Question'),category(r),r.get('reference',{}).get('Cross_Page_Table','unknown'),r.get('status'),raw,s.get('score') if raw is not None else None,_state(raw),s.get('target_coverage'),'；'.join(s.get('missing_targets',[])),full_rank,r.get('elapsed_seconds'),r['ID'] in included,ids])
        for kind in KINDS:
            subset=[r for r in scored if kind=='整體' or category(r)==kind]
            original=[r for r in result['rows'] if (kind=='整體' or category(r)==kind) and valid(r,r.get('scores',{}).get(stage))]
            if not subset and not original:continue
            ss=[r['scores'][stage] for r in subset];n=len(ss)
            tables[NAMES[1]].append(meta+[{'retrieval':'檢索子項','returned':'召回父項後'}[stage],kind,n,len(original),len(original)-n,avg(s['raw_score'] for s in ss),avg(s['score'] for s in ss),sum(s['raw_score']>=9.9999 for s in ss),sum(s['raw_score']>=9.9999 for s in ss)/n if n else None])
            previous=(0.,0.,0.)
            for top in range(1,k+1):
                values=[prefix(s,top) for s in ss]
                current=(avg(v[0] for v in values),avg(v[1] for v in values),sum(v[2] for v in values)/n if n else None)
                tables[NAMES[2]].append(meta+[{'retrieval':'檢索子項','returned':'召回父項後'}[stage],kind,top,n,current[0],current[1],sum(v[2] for v in values),current[2]])
                if top%5==0 or top==k:
                    gains=[round(a-b,4) if a is not None and b is not None else None for a,b in zip(current,previous)]
                    tables[NAMES[3]].append(meta+[{'retrieval':'檢索子項','returned':'召回父項後'}[stage],kind,((top-1)//5)*5+1,top,n,*gains]);previous=current
    pair_common={}
    for source,result in results:
        base=info(result,source)
        versions={}
        for r in result.get('rows',[]):
            before=r.get('scores',{}).get('returned');after=r.get('scores',{}).get('rerank')
            if before is None or after is None:continue
            rule=before.get('scoring_rule') or base[6]
            if rule!=(after.get('scoring_rule') or base[6]):continue
            versions.setdefault(rule,set())
            if valid(r,before) and valid(r,after):versions[rule].add(r['ID'])
        for rule,ids in versions.items():
            key=(base[0],rule)
            pair_common[key]=ids if key not in pair_common else pair_common[key]&ids
    for source,result in results:
        base=info(result,source);top=min(10,result['settings']['retrieve_k'],result.get('settings',{}).get('evidence_k',10))
        pairs=[]
        for row in result.get('rows',[]):
            scores=row.get('scores',{});after=scores.get('rerank');before=scores.get('returned')
            if after is None:continue
            okay=valid(row,before) and valid(row,after) and (before.get('scoring_rule') or base[6])==(after.get('scoring_rule') or base[6])
            meta=_stage_meta(base,after);b=prefix(before,top) if okay else (None,None,None);a=prefix(after,top) if okay else (None,None,None)
            diff=[round(a[i]-b[i],4) if okay else None for i in (0,1)]
            change=lambda v:'改善' if v>0 else ('退步' if v<0 else '不變')
            tables[NAMES[7]].append(meta+[row['ID'],row.get('Question'),category(row),row.get('reference',{}).get('Cross_Page_Table','unknown'),top,b[0],a[0],diff[0],b[1],a[1],diff[1],change(diff[0]) if okay else None,change(diff[1]) if okay else None,(_state(b[0])+'→'+_state(a[0])) if okay else None,'同題同版本' if okay else '未配對：版本不同、待確認或執行失敗'])
            if okay and row['ID'] in pair_common.get((base[0],meta[6]),set()):pairs.append((row,before,after))
        if not pairs:continue
        meta=_stage_meta(base,pairs[0][2]);unit='來源證據／父項召回後'
        for kind in KINDS:
            subset=[p for p in pairs if kind=='整體' or category(p[0])==kind]
            if not subset:continue
            n=len(subset)
            for rank in range(1,top+1):
                b=[prefix(p[1],rank) for p in subset];a=[prefix(p[2],rank) for p in subset]
                bm=[avg(v[i] for v in b) for i in (0,1)];am=[avg(v[i] for v in a) for i in (0,1)]
                rates=[sum(v[2] for v in group)/n for group in (b,a)]
                tables[NAMES[6]].append(meta+[unit,kind,rank,n,bm[0],am[0],bm[1],am[1],*rates])
                if rank!=top:continue
                dr=round(am[0]-bm[0],4);dw=round(am[1]-bm[1],4)
                tables[NAMES[5]].append(meta+[unit,kind,rank,n,bm[0],am[0],dr,bm[1],am[1],dw,*rates])
                times=[p[0].get('timings',{}).get('rerank') for p in subset];known_times=[t for t in times if t is not None]
                usages=[p[0].get('query',{}).get('rerank',{}).get('total_tokens') for p in subset]
                tokens=[v for v in usages if type(v) is int];total=sum(tokens) if tokens else None
                per=lambda gain:round(gain/(total/n/1000),4) if len(tokens)==n and total else None
                tables[NAMES[8]].append(meta+[kind,rank,n,dr,dw,avg(known_times),len(known_times),total,len(tokens),per(dr),per(dw)])
    # 報告主要數值放前面；版本、來源與比較群放最後供追溯。
    output=[]
    for name in NAMES:
        rows=tables[name]
        if name!=NAMES[0]:
            columns=list(range(1,6))+list(range(8,len(rows[0])))+[0,6,7]
            rows=[[row[i] for i in columns] for row in rows]
        output.append((name,rows))
    return output


def export_comparison(results,settings):
    """另存比較報告；保留來源結果，無API或索引存取。"""
    from dataclasses import replace
    from Code_2.functions.experiments.export_output import reserve_qa_run
    from Code_2.functions.experiments.eval_workbook import write_xlsx
    from Code_2.config.evaluation import EvaluationSettings
    if not EvaluationSettings().enabled:raise ValueError('Excel實驗功能已停用')
    paths=reserve_qa_run(replace(settings,export_enabled=True),mode='retrieve')
    manifest={'schema_version':'financial-report-tables/1.0','report_kind':'comparison_tables',
              'sources':[{'name':name,'output_dir':r.get('output_dir'),'scoring_rule':r.get('scoring_rule')} for name,r in results]}
    (paths['json']).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    target=paths['json'].with_name('results.xlsx')
    try:target.write_bytes(write_xlsx(build_tables(results),presentation=True))
    except Exception:
        manifest.update(export_status='failed')
        paths['json'].write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    return {'output_dir':str(target.parent),'export_status':'saved'}


def main():
    parser=argparse.ArgumentParser(description='已保存結果產生九頁作圖表，不呼叫模型')
    parser.add_argument('sources',nargs='+',type=Path)
    args=parser.parse_args()
    from Code_2.config.embedding import Settings
    from Code_2.config.evaluation import EvaluationSettings
    if not EvaluationSettings().enabled:raise ValueError('Excel實驗功能已停用')
    sources=[]
    for p in args.sources:
        raw=p.read_bytes();doc=json.loads(raw.decode('utf-8'))
        sources.append((str(p.resolve())+' SHA256='+hashlib.sha256(raw).hexdigest(),doc))
    print(json.dumps(export_comparison(sources,Settings()),ensure_ascii=False))


if __name__=='__main__':main()
