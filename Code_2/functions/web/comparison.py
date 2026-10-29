"""多索引依序執行；沿用單索引核心，各自保存且不融合證據。"""
from Code_2.functions.qa.catalog import list_indexes,select_index


def run_comparison(data,settings,execute):
    from Code_2.functions.web.service import task_outcome
    indexes=data['indexes'];base={k:v for k,v in data.items() if k!='indexes'}
    # 全部先核對，避免一半執行後才發現所選集合不存在。
    available=list_indexes(settings)
    for item in indexes:select_index(available,item['backend'],item['collection'])
    results=[];stopped=False
    for number,item in enumerate(indexes,1):
        entry={'backend':item['backend'],'collection':item['collection']}
        if stopped:
            results.append({**entry,'outcome':'not_run','error':'前一索引執行失敗，未繼續呼叫模型'});continue
        print(f"索引比較 {number}/{len(indexes)}：{item['backend']} {item['collection']}",flush=True)
        try:
            result=execute({**base,**item},settings)
            outcome=task_outcome(result)
            results.append({**entry,'outcome':outcome,'result':result})
            payload=result.get('query',result.get('evaluation',{}))
            stopped=payload.get('status')=='failed' or payload.get('export_status')=='failed' or bool(payload.get('summary',{}).get('failed'))
        except Exception as error:
            results.append({**entry,'outcome':'failed','error':f'索引執行失敗（{type(error).__name__}），未重試'})
            stopped=True
    output={'action':data['action'],'multi':True,'results':results}
    # EXPERIMENT_ONLY：同次多方法另存九頁比較表，不重新檢索或融合證據。
    batches=[(r['collection'],r['result']['evaluation']) for r in results
             if r.get('result',{}).get('evaluation',{}).get('schema_version')=='financial-evaluation/1.0']
    if batches and data.get('export_enabled',settings.export_enabled):
        from Code_2.functions.experiments.report_tables import export_comparison
        try:output['comparison_report']=export_comparison(batches,settings)
        except (OSError,ValueError,TypeError) as error:
            output['comparison_report']={'export_status':'failed','error':f'比較表匯出失敗（{type(error).__name__}）；各方法原報告仍保留'}
    return output
