"""網頁與工作程序共用參數驗證；只允許已授權的OCR倍率與表格模式。"""
import math
from dataclasses import replace


def request_settings(settings, request):
    if not isinstance(request.get('ocr'), bool):
        raise ValueError('OCR 設定錯誤')
    scale = request.get('ocr_scale', settings.ocr.scale)
    if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
        raise ValueError('OCR 放大倍率必須是大於0的有限數字')
    parser = request.get('pdf_parser', settings.pdf_parser)
    if parser not in ('docling', 'inspector'):
        raise ValueError('PDF解析器須為Docling或pdf-inspector')
    mode = request.get('table_mode', settings.table_mode)
    if mode not in ('fast', 'accurate'):
        raise ValueError('表格模式必須是 FAST 或 ACCURATE')
    chunking = settings.chunking
    if request.get('stage') == 'chunk':
        selected = request.get('chunk_mode', chunking.mode)
        if selected not in ('original', 'parent_child'):
            raise ValueError('切塊模式須為original或parent_child')
        changes = {'mode': selected}
        for name in ('text_embedding_mode', 'table_embedding_mode'):
            value = request.get(name, getattr(chunking, name))
            if value not in ('body', 'description', 'full'):
                raise ValueError('Embedding脈絡模式須為body／description／full')
            changes[name] = value
        for name in ('parent_limit', 'child_target', 'recursive_threshold'):
            value = request.get(name, getattr(chunking, name))
            if type(value) is not int or value < 1:
                raise ValueError(f'{name}須為正整數')
            changes[name] = value
        chunking = replace(chunking, **changes)
    return replace(settings, ocr_enabled=request['ocr'], ocr=replace(settings.ocr, scale=float(scale)),
                   table_mode=mode, chunking=chunking, pdf_parser=parser)
