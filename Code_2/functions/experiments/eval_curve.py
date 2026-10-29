"""EXPERIMENT_ONLY：同次召回的固定扣分累積曲線；不呼叫模型。"""
from statistics import mean


def build_curves(rows, retrieve_k, *, metric="weighted"):
    if metric not in ('weighted','raw'):raise ValueError('未知曲線分數種類')
    result={}
    for stage in ('retrieval','returned','rerank'):
        valid=[r['scores'][stage] for r in rows if r.get('status') not in
               ('failed','not_run','corpus_unavailable') and
               r.get('scores',{}).get(stage,{}).get('score') is not None]
        if not valid:continue
        points=[];previous=0.0
        for k in range(1,retrieve_k+1):
            value=round(mean(sum(c['raw_score'] if metric=='raw' else c['score'] for c in s['contributions'] if c['rank']<=k) for s in valid),4)
            points.append({'k':k,'mean_score':value,'gain':round(value-previous,4)})
            previous=value
        blocks=[]
        for start in range(1,retrieve_k+1,5):
            end=min(start+4,retrieve_k)
            baseline=points[start-2]['mean_score'] if start>1 else 0
            blocks.append({'start':start,'end':end,'mean_score':points[end-1]['mean_score'],
                           'gain':round(points[end-1]['mean_score']-baseline,4)})
        final=points[-1]['mean_score']
        rates=sorted({s['rank_penalty'] for s in valid if s.get('rank_penalty') is not None})
        rate=0.0 if metric=='raw' else (rates[0] if len(rates)==1 and all(s.get('rank_penalty') is not None for s in valid) else None)
        result[stage]={'metric':metric,'count':len(valid),'retrieve_k':retrieve_k,'rank_penalty':rate,
            'rank_penalties':rates if metric=='weighted' else [0.0],
            'points':points,'blocks':blocks,
            'first_full_score_k':next((p['k'] for p in points if p['mean_score']==final),None) if final>0 else None,
            'best_block':max(blocks,key=lambda b:b['gain']) if final>0 else None,
            'meaning':('原始分數：各項目標等額，不扣排名分。' if metric=='raw' else '排名加權分數沿用已保存各項貢獻；新版每項每晚一名扣該項配分/原始K，舊報告維持來源扣分。')+'有Required_Numbers的新版題目只按必要數字跨chunk補齊，metadata不擋分；舊版依保存規則，無數字標準者沿用年度×標題；以逐題scoring_rule為準。有效排名採同必回父項去重；非重新檢索或重排序的實測。'}
    return result
