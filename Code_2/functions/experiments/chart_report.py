"""EXPERIMENT_ONLY：從已完成評分製圖並另存；不重查索引或呼叫模型。"""
import copy
import json
import math
import time
import hashlib
from dataclasses import replace
from html import escape
from Code_2.config.evaluation import EvaluationSettings
from Code_2.config.qa import QASettings
from Code_2.functions.experiments.eval_curve import build_curves
from Code_2.functions.experiments.eval_scoring import SUPPORTED_RULES
from Code_2.functions.experiments.eval_run import export_batch
from Code_2.functions.experiments.export_output import reserve_qa_run


def validate_source(data,settings):
    if not EvaluationSettings().enabled:raise ValueError('Excel實驗功能已停用')
    if set(data)-{'action','source_run','source'}:raise ValueError('製圖欄位無效')
    if bool(data.get('source_run'))==bool(data.get('source')):raise ValueError('請提供一份來源結果')
    if data.get('source_run'):
        from Code_2.functions.web.service import report_path
        path=report_path(settings,data['source_run'],'result.json')
        if path.stat().st_size>128*1024*1024:raise ValueError('來源報告過大')
        raw=path.read_bytes()
        source=json.loads(raw.decode('utf-8'))
        source['chart_source_sha256']=hashlib.sha256(raw).hexdigest()
    else:source=data['source']
    if not isinstance(source,dict) or source.get('scoring_rule') not in SUPPORTED_RULES:
        raise ValueError('僅支援年度×標題雙分數報告；舊報告不可假填原始分數')
    k=source.get('settings',{}).get('retrieve_k')
    if type(k) is not int or not 1<=k<=QASettings().max_retrieve_k:raise ValueError('來源召回數無效')
    rows=source.get('rows')
    if not isinstance(rows,list) or not 1<=len(rows)<=EvaluationSettings().max_rows:raise ValueError('來源題目數無效')
    clean=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('scores',{}),dict):raise ValueError('來源評分無效')
        stages={}
        for stage,value in row.get('scores',{}).items():
            if stage not in ('retrieval','returned','rerank') or not isinstance(value,dict):raise ValueError('來源評分階段無效')
            if value.get('score') is None:continue
            parts=value.get('contributions')
            if not isinstance(parts,list) or len(parts)>5000:raise ValueError('來源得分項目無效')
            for part in parts:
                if not isinstance(part,dict) or type(part.get('rank')) is not int or not 1<=part['rank']<=k:raise ValueError('來源排名無效')
                for field in ('score','raw_score'):
                    v=part.get(field)
                    if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=10:raise ValueError('來源分數無效')
            if any(sum(p[field] for p in parts)>10.0001 for field in ('score','raw_score')):raise ValueError('來源總分超過10')
            stages[stage]={key:copy.deepcopy(value.get(key)) for key in ('score','raw_score','weighted_score','contributions','page_coverage','title_coverage','target_coverage','retrieve_k','rank_penalty','scoring_rule','rank_weighting')}
            stages[stage].update(top20=[],missing_pages=value.get('missing_pages',[]),missing_titles=value.get('missing_titles',[]),
                missing_targets=value.get('missing_targets',[]),target_hits=value.get('target_hits',{}),title_hits=value.get('title_hits',{}))
        clean.append({'ID':str(row.get('ID','')),'Question':str(row.get('Question','')),'status':row.get('status'),
            'score':row.get('score'),'raw_score':row.get('raw_score'),'weighted_score':row.get('weighted_score'),
            'score_stage':row.get('score_stage'),'scores':stages})
    return {'schema_version':'financial-evaluation/1.0','scoring_rule':source['scoring_rule'],
        'filename':source.get('filename','未保存結果'),'sheet':source.get('sheet',''),
        'settings':{'retrieve_k':k},'index':source.get('index',{}),'summary':source.get('summary',{}),
        'source_run':data.get('source_run') or source.get('source_run'),
        'chart_source_sha256':source.get('chart_source_sha256'),'rows':clean}


def chart_svg(result):
    plots=[(kind,stage,c) for kind,family in [('原始',result['raw_curves']),('排名加權',result['curves'])] for stage,c in family.items()]
    labels={'retrieval':'原始檢索','returned':'父項召回後','rerank':'重排序'}
    body=[]
    for n,(kind,stage,c) in enumerate(plots):
        offset=n*290
        body.append(f'<g transform="translate(0,{offset})"><text x="50" y="25" font-size="18">{escape(labels[stage]+kind+"平均得分")}</text>')
        for v in (0,2,4,6,8,10):
            y=240-v*19
            body.append(f'<line x1="50" y1="{y}" x2="720" y2="{y}" stroke="#ddd"/><text x="20" y="{y}" font-size="12">{v}</text>')
        points=' '.join(f"{50+(p['k']-1)*670/max(1,c['retrieve_k']-1)},{240-p['mean_score']*19}" for p in c['points'])
        body.append(f'<polyline points="{points}" fill="none" stroke="#287759" stroke-width="2"/>')
        body.append(f'<text x="50" y="265" font-size="13">有效Top 1～{c["retrieve_k"]}；{c["count"]}題；滿分10</text></g>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="760" height="'+str(max(290,290*len(plots)))+'" style="background:white;font-family:sans-serif">'+''.join(body)+'</svg>').encode('utf-8')


def make_report(source,settings):
    started=time.perf_counter()
    result=copy.deepcopy(source);k=result['settings']['retrieve_k']
    result.update(status='completed',report_kind='chart_statistics',elapsed_seconds=0,
        curves=build_curves(result['rows'],k),raw_curves=build_curves(result['rows'],k,metric='raw'))
    if not result['curves']:raise ValueError('來源沒有可評分結果，無法製圖')
    result['elapsed_seconds']=round(time.perf_counter()-started,6)
    paths=reserve_qa_run(replace(settings,export_enabled=True), mode=source.get('settings', {}).get('mode', 'retrieve'))
    result.update(export_status='saved',output_dir=str(paths['json'].parent),created_at=paths['created_at'])
    svg=paths['json'].with_name('charts.svg')
    try:
        with svg.open('xb') as stream:stream.write(chart_svg(result))
        export_batch(paths,result)
    except BaseException:
        svg.unlink(missing_ok=True)
        raise
    return result
