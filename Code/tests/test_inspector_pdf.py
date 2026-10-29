"""解析器邊界與OCR回退；假inspector輸出，不冒充真實模型辨識。"""
import sys,unittest
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.ingestion.inspector_pdf import InspectorSession
from schemas import MarkdownDocument,MarkdownPage


class InspectorTests(unittest.TestCase):
    def page(self,index,text='## 十一、<u>應收票據及帳款淨額</u>',needs=False):
        return SimpleNamespace(page=index,markdown=text,needs_ocr=needs,ocr_reason='unreliable' if needs else None)

    def api(self,pages):return SimpleNamespace(extract_pages_markdown=lambda source:SimpleNamespace(pages=pages))

    def test_original_page_numbers_cached_and_formatting_removed(self):
        session=InspectorSession(replace(SETTINGS,pdf_parser='inspector'))
        calls=[]
        fake=self.api([self.page(0),self.page(1)])
        with patch.dict(sys.modules,{'pdf_inspector':fake}),patch('functions.ingestion.inspector_pdf.version',return_value='test'):
            runtime={};source=Path('2024Q4_2330_Financial_Report.pdf')
            first=session.convert(source,2,runtime,calls.append,page_range=(2,2))
            second=session.convert(source,2,runtime,page_range=(1,1))
        self.assertEqual(first.pages[0].pdf_page,2)
        self.assertIn('2330_2024_P2',first.markdown)
        self.assertNotIn('<u>',first.markdown)
        self.assertEqual(calls[0].page_no,2)
        self.assertEqual(second.pages[0].pdf_page,1)
        self.assertEqual(len(runtime['inspector']['page_provenance']),2)

    def test_requires_ocr_does_not_silently_enable_it(self):
        session=InspectorSession(replace(SETTINGS,pdf_parser='inspector',ocr_enabled=False))
        with patch.dict(sys.modules,{'pdf_inspector':self.api([self.page(0,'',True)])}),patch('functions.ingestion.inspector_pdf.version',return_value='test'):
            with self.assertRaisesRegex(ValueError,'請啟用OCR'):
                session.convert(Path('2024Q4_2330_Financial_Report.pdf'),1,{})

    def test_fallback_calls_existing_converter_and_records_provenance(self):
        session=InspectorSession(replace(SETTINGS,pdf_parser='inspector',ocr_enabled=True))
        result=MarkdownDocument('','',(MarkdownPage(1,'表格內容','text_extracted',(),()),),(),None)
        with patch.dict(sys.modules,{'pdf_inspector':self.api([self.page(0,'',True)])}),patch('functions.ingestion.inspector_pdf.version',return_value='test'),patch('functions.ingestion.pdf_to_markdown.create_converter',return_value=('converter',{})) as setup,patch('functions.ingestion.pdf_to_markdown.convert_pdf',return_value=result) as convert:
            runtime={};session.convert(Path('2024Q4_2330_Financial_Report.pdf'),1,runtime)
        self.assertEqual(setup.call_args.args[0].pdf_parser,'docling')
        self.assertEqual(convert.call_args.kwargs['page_range'],(1,1))
        self.assertEqual(runtime['inspector']['page_provenance'][0]['engine'],'docling')

    def test_missing_or_duplicate_pages_are_not_accepted(self):
        session=InspectorSession(replace(SETTINGS,pdf_parser='inspector'))
        with patch.dict(sys.modules,{'pdf_inspector':self.api([self.page(0),self.page(0)])}):
            with self.assertRaisesRegex(ValueError,'頁序'):
                session.convert(Path('2024Q4_2330_Financial_Report.pdf'),2,{})


if __name__=='__main__':unittest.main()
