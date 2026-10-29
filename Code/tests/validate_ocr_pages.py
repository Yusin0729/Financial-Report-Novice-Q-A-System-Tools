"""明確指定頁序的小範圍真實測試；不是整批轉換或品質合格證明。

EXPERIMENT_ONLY 寫檔集中 export_output；--no-export 保留記憶體處理。
"""
import argparse
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.ingestion.pdf_to_markdown import create_converter, serialize_document, source_hash, conversion_versions
from functions.integrations.docling_mineru_ocr import collect_diagnostics


def validate(source, pages, settings):
    import psutil
    import pypdfium2 as pdfium
    from docling.datamodel.base_models import ConversionStatus
    before=source_hash(source)
    with pdfium.PdfDocument(source) as pdf:
        count=len(pdf)
    if not pages or any(p<1 or p>count for p in pages):
        raise ValueError('測試頁序不合法')
    record={'source':str(source), 'sha256':before, 'selected_physical_pages':pages,
            'synthetic':source.stem.startswith('synthetic_'), 'settings':settings.pdf_manifest(),
            'versions':conversion_versions(), 'pages':[], 'ocr_diagnostics':[]}
    documents={}
    stop=threading.Event()
    peak={'rss_bytes':0,'private_bytes':0}
    def sample():
        process=psutil.Process()
        while not stop.is_set():
            memory=process.memory_info()
            peak['rss_bytes']=max(peak['rss_bytes'],memory.rss)
            peak['private_bytes']=max(peak['private_bytes'],getattr(memory,'private',0))
            stop.wait(.2)
    monitor=threading.Thread(target=sample,daemon=True)
    monitor.start()
    start=time.perf_counter()
    converter,options=create_converter(settings)
    record['pipeline_options']=options
    try:
        for page in pages:
            started=time.perf_counter()
            print(f'小範圍實測：PDF 實體第 {page} 頁',flush=True)
            try:
                result=converter.convert(source,page_range=(page,page),raises_on_error=False)
                item={'pdf_page':page,'status':result.status.value,
                      'errors':[e.model_dump(mode='json') for e in result.errors]}
                if result.status==ConversionStatus.SUCCESS:
                    document=serialize_document(result.document,count,settings.table_format,selected_pages=[page])
                    documents[page]=document
                    item.update(text_status=document.pages[0].status, warnings=list(document.warnings),
                                html_table_count=document.raw_markdown.count('<table'))
            except Exception as exc:
                item={'pdf_page':page,'status':'failed','error':f'{type(exc).__name__}: {exc}'}
            item['elapsed_seconds']=round(time.perf_counter()-started,3)
            record['pages'].append(item)
            print(item,flush=True)
    finally:
        record['ocr_diagnostics']=collect_diagnostics(converter)
        record['elapsed_seconds']=round(time.perf_counter()-start,3)
        record['source_unchanged']=source_hash(source)==before
        stop.set();monitor.join()
        record['memory_peak']=peak
        # EXPERIMENT_ONLY：移除此呼叫不改變上方記憶體資料流。
        from functions.experiments.export_output import export_ocr_validation
        target=export_ocr_validation(settings,source,record,documents)
        print(f'實測輸出：{target}；峰值：{peak}',flush=True)
    return record,documents


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf',required=True,type=Path)
    parser.add_argument('--pages',required=True,type=int,nargs='+')
    parser.add_argument('--no-export',action='store_true')
    args=parser.parse_args()
    record,_=validate(args.pdf.resolve(),args.pages,replace(SETTINGS,ocr_enabled=True,export_enabled=not args.no_export))
    sys.exit(0 if all(p['status']=='success' for p in record['pages']) else 1)
