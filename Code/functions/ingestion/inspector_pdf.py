"""pdf-inspector整頁原生文字解析；OCR／空白回退既有Docling，不混拼正文與表格。"""
import re
from dataclasses import replace
from importlib.metadata import version
from types import SimpleNamespace
from schemas import MarkdownDocument, MarkdownPage


class InspectorSession:
    def __init__(self, settings):
        self.settings = settings
        self.source = None
        self.pages = None
        self.fallback = None

    def _load(self, source, count, runtime):
        if self.pages is not None:
            if self.source != source.resolve():
                raise ValueError('解析器快取不能混用不同來源PDF')
            return
        runtime['stage'] = 'inspector_native_extraction'
        import pdf_inspector
        from functions.ingestion.timings import wall_timer
        with wall_timer(runtime,'inspector_extraction'):
            result = pdf_inspector.extract_pages_markdown(str(source))
        pages = {page.page+1:page for page in result.pages}
        if len(pages) != count or set(pages) != set(range(1,count+1)):
            raise ValueError('pdf-inspector頁序缺失、重複或超出原PDF')
        self.source, self.pages = source.resolve(), pages
        runtime['inspector'] = {'version':version('pdf-inspector'),
            'native_extraction_scope':'all_pages_once_cached; export_selected_pages_only',
            'page_provenance':[]}

    def convert(self, source, count, runtime, callback=None, *, page_range=None):
        self._load(source,count,runtime)
        first,last = page_range or (1,count)
        if not 1 <= first <= last <= count:
            raise ValueError('選定頁序超出原始PDF')
        pages,warnings=[],['pdf-inspector試驗模式：管線表格不等於保留HTML合併儲存格，數值與欄列仍需人工核對']
        provenance={row['pdf_page']:row for row in runtime['inspector']['page_provenance']}
        for number in range(first,last+1):
            page=self.pages[number]
            native=page.markdown
            requires_fallback=page.needs_ocr or not native.strip()
            if requires_fallback:
                if not self.settings.ocr_enabled:
                    raise ValueError(f'pdf-inspector第{number}頁需OCR或原生輸出空白；請啟用OCR後重試，未輸出假成功')
                runtime['stage']='inspector_docling_fallback'
                from functions.ingestion.pdf_to_markdown import create_converter,convert_pdf
                fallback_settings=replace(self.settings,pdf_parser='docling')
                if self.fallback is None:self.fallback=create_converter(fallback_settings)
                result=convert_pdf(source,count,fallback_settings,runtime,None,
                    page_range=(number,number),converter_bundle=self.fallback)
                rendered=result.pages[0]
                if rendered.status=='no_text_extracted':
                    raise ValueError(f'第{number}頁經Docling／OCR回退仍無文字')
                pages.append(rendered);warnings.extend(result.warnings)
                provenance[number]={'pdf_page':number,'engine':'docling','fallback':True,
                    'reason':getattr(page,'ocr_reason',None) or 'needs_ocr_or_empty_native',
                    'ocr_strategy':'existing_pdf_aware_regions'}
            else:
                # 移除inspector的行內底線／字型HTML格式；保留文字與表格管線，不猜數值或修欄。
                native=re.sub(r'</?(?:u|b|i|em|strong)>','',native,flags=re.I)
                pages.append(MarkdownPage(number,native,'text_extracted',(),()))
                provenance[number]={'pdf_page':number,'engine':'pdf-inspector','fallback':False}
            runtime['inspector']['page_provenance']=list(provenance.values())
            if callback:callback(SimpleNamespace(kind='page_completed',completed_pages=number-first+1,
                total_pages=last-first+1,page_no=number,success=True))
        from functions.markdown_processing.file_identity import source_identity
        from functions.markdown_processing.page_markers import format_page_marker
        identity=source_identity(source)
        marked='\n'.join(format_page_marker(p.pdf_page,identity)+'\n\n'+p.markdown for p in pages)
        return MarkdownDocument('\n'.join(p.markdown for p in pages),marked,tuple(pages),
                                tuple(dict.fromkeys(warnings)),None)
