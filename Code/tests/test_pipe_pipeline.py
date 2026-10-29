"""新raw格式與本機後續流程；不執行OCR或模型。"""
import sys
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_markdown import sample_document
from functions.ingestion.pdf_to_markdown import serialize_document
from functions.ingestion.section_markers import assemble_selected_pages
from functions.ingestion.page_selection import select_from_toc
from functions.markdown_processing.mark_headings import mark_missing_headings
from functions.markdown_processing.page_cleanup import remove_standalone_page_numbers
from functions.markdown_processing.comment_tagging import tag_comments
from functions.chunking.chunks import chunk_tagged_legacy as chunk_tagged
from schemas import TaggingMetadata, MarkdownPage
from schemas import MarkdownDocument
from config.settings import SETTINGS

TABLE = '| 項目 | 2025 | 2024 |\n| --- | ---: | ---: |\n| 1. 方法 | (123) | -5 |\n'


class PipePipelineTests(unittest.TestCase):
    def test_first_stage_excludes_cover_and_preserves_pdf_page_numbers(self):
        import pypdfium2 as pdfium
        import main
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(SETTINGS, project_root=Path(tmp), export_enabled=False)
            settings.source_dir.mkdir()
            path = settings.source_dir / '2025Q4_2303_Financial_Report.pdf'
            with pdfium.PdfDocument.new() as pdf:
                for _ in range(15):
                    pdf.new_page(100, 100).close()
                pdf.save(path)
            calls = []
            def convert(source, count, config, runtime, progress, *, page_range, converter_bundle):
                calls.append(page_range)
                pages = tuple(MarkdownPage(p, '## 一、公司沿革\n' + TABLE if p == 14 else '文字',
                                           'text_extracted', (), ()) for p in range(page_range[0], page_range[1]+1))
                return MarkdownDocument('', '', pages, (), None)
            with patch('functions.ingestion.pdf_to_markdown.create_converter', return_value=(None, {})), patch(
                    'functions.ingestion.pdf_to_markdown.convert_pdf', side_effect=convert), patch(
                    'functions.ingestion.page_selection.select_from_toc',
                    return_value={'toc_pages':[2], 'notes_start':14, 'audit_pages':(4,7)}):
                record = main.run_markdown(path, settings)
            self.assertEqual(record['status'], 'converted_needs_review')
            self.assertEqual(calls, [(2,3), (4,7), (14,15)])
            self.assertEqual(record['selection']['selected_pdf_pages'], [4,5,6,7,14,15])
            self.assertTrue(record['document'].markdown.startswith('<會計師查核報告>'))
            self.assertNotIn('_P1 -->', record['document'].markdown)

    def test_continued_pipe_table_retains_full_parent_and_page_children(self):
        raw = ('<!-- Page: 2303_2025_P14 -->\n## 一、公司沿革\n' + TABLE +
               '接 次 頁\n<!-- Page: 2303_2025_P15 -->\n' + TABLE)
        tagged = tag_comments(raw, None, TaggingMetadata(report_year='2025', stock_code='2303')).markdown
        result = chunk_tagged(tagged, identity=('2025', '2303'), source_sha256='a'*64)
        self.assertEqual(len(result.document['parents']), 1)
        self.assertEqual([c['page'] for c in result.document['chunks']], [[14], [15]])
        self.assertTrue(all(c['content_type']=='table' for c in result.document['chunks']))
        self.assertEqual(result.document['parents'][0]['content'].count('| 1. 方法'), 2)

    def test_official_serializer_keeps_values_and_footnotes(self):
        result = serialize_document(sample_document(), 3, 'markdown')
        self.assertNotIn('<table', result.markdown)
        self.assertIn('|', result.markdown)
        self.assertIn('10.25%', result.markdown)
        self.assertIn('表下注：金額含稅', result.markdown)
        self.assertTrue(any('合併儲存格' in w for w in result.warnings))

    def test_pipe_toc_page_selection(self):
        toc = ('目錄\n| 項目 | 頁次 |\n| --- | --- |\n| 聲明書 | 3 |\n'
               '| 會計師查核報告 | 4~7 |\n| 合併財務報告附註 | 14~89 |\n')
        self.assertEqual(select_from_toc(toc, '', 89)['notes_start'], 14)

    def test_sections_and_pipe_table_survive_processed_tagged_chunk(self):
        pages = (MarkdownPage(4, '查核報告', 'text_extracted', (), ()),
                 MarkdownPage(14, '## 一、公司沿革\n說明\n' + TABLE, 'text_extracted', (), ()))
        raw = assemble_selected_pages(pages, ('2025', '2303'), 4, 14)
        self.assertTrue(raw.startswith('<會計師查核報告>\n<!-- Page: 2303_2025_P4 -->'))
        self.assertIn('<note>\n<合併財務報告附註>\n<!-- Page: 2303_2025_P14 -->', raw)
        processed = remove_standalone_page_numbers(mark_missing_headings(raw).markdown)[0]
        self.assertIn(TABLE, processed)
        tagged = tag_comments(processed, None, TaggingMetadata(report_year='2025', stock_code='2303')).markdown
        self.assertIn('<table_start>\n' + TABLE, tagged)
        result = chunk_tagged(tagged, identity=('2025', '2303'), source_sha256='a'*64)
        table = next(c for c in result.document['chunks'] if c['content_type'] == 'table')
        self.assertEqual(table['years'], [2024, 2025])
        self.assertIn(TABLE, table['content'])
        self.assertEqual(len(result.document['parents']), 1)


if __name__ == '__main__':
    unittest.main()
