"""
程式主要目的與功能：
本測試模組用於驗證 PDF 轉 Markdown 轉換規格與邊界行為，涵蓋：
1. 空白頁頁序保持與狀態標記驗證。
2. 表格合併欄位（HTML colspan/rowspan）、財務符號（括號負值、負號、百分比）與表下注保留驗證。
3. 頁序不完整時的例外錯誤拋出檢查。
4. 跨頁項目關聯完整性檢查。
5. 停用實驗輸出（export_enabled=False）時純記憶體回傳與來源雜湊檢查。
6. 轉換失敗時僅輸出 manifest.json 之保護機制檢查。

使用之外部套件與用途：
- docling_core: 建立人工合成的 DoclingDocument 結構進行單元測試，避免依賴外部真實模型推論。
"""

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docling_core.types.doc import (
    BoundingBox, ContentLayer, DocItemLabel, DoclingDocument, ProvenanceItem,
    Size, TableCell, TableData,
)
from functions.experiments.export_output import export_markdown_run
from functions.ingestion.pdf_to_markdown import serialize_document
from main import run_markdown
from config.settings import SETTINGS


def provenance(page):
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=0, t=10, r=10, b=0), charspan=(0, 10))


def sample_document():
    document = DoclingDocument(name="人工測試結構")
    for page in (1, 2, 3):
        document.add_page(page_no=page, size=Size(width=100, height=100))
    document.add_text(label=DocItemLabel.TEXT, text="新臺幣仟元；(1,234.50)；-5%；2025", prov=provenance(1))
    document.add_text(label=DocItemLabel.PAGE_FOOTER, text="印刷頁碼 99", prov=provenance(3), content_layer=ContentLayer.FURNITURE)
    table = document.add_table(data=TableData(num_rows=1, num_cols=2, table_cells=[
        TableCell(text="合併欄位 10.25%", col_span=2, start_row_offset_idx=0,
                  end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=2),
    ]), prov=provenance(1))
    footnote = document.add_text(label=DocItemLabel.FOOTNOTE, text="表下注：金額含稅", prov=provenance(1))
    table.footnotes.append(footnote.get_ref())
    return document


class MarkdownTests(unittest.TestCase):
    def test_blank_page_keeps_original_sequence_and_is_flagged(self):
        converted = serialize_document(sample_document(), 3, "html")
        self.assertEqual([page.pdf_page for page in converted.pages], [1, 2, 3])
        self.assertEqual(converted.pages[1].status, "no_text_extracted")
        self.assertIn("<!-- PDF_PAGE: 2 -->", converted.markdown)
        self.assertIn("<!-- PDF_PAGE: 3 -->", converted.markdown)
        self.assertIn("印刷頁碼 99", converted.pages[2].markdown)
        self.assertTrue(converted.warnings)

    def test_html_spans_financial_signs_and_footnote_are_preserved(self):
        converted = serialize_document(sample_document(), 3, "html")
        for text in ('colspan="2"', "(1,234.50)", "-5%", "10.25%", "新臺幣仟元", "表下注：金額含稅"):
            self.assertIn(text, converted.raw_markdown)
            self.assertIn(text, converted.pages[0].markdown)

    def test_missing_page_is_error_not_renumbered(self):
        document = sample_document()
        del document.pages[2]
        with self.assertRaisesRegex(ValueError, "頁序不完整"):
            serialize_document(document, 3, "html")

    def test_cross_page_item_keeps_all_sources_without_guessing_split(self):
        document = sample_document()
        document.tables[0].prov.append(provenance(3))
        converted = serialize_document(document, 3, "html")
        ref = document.tables[0].self_ref
        for index in (0, 2):
            self.assertIn(ref, converted.pages[index].cross_page_item_refs)
        self.assertIn('colspan="2"', converted.pages[0].markdown)
        self.assertNotIn('colspan="2"', converted.pages[2].markdown)
        self.assertIn("CROSS_PAGE_ITEMS", converted.markdown)

    def test_export_disabled_returns_memory_without_output(self):
        source = SETTINGS.source_dir / "2330" / "2025Q4_2330_Financial_Report.pdf"
        if not source.is_file():
            found = list(SETTINGS.source_dir.rglob("*.pdf"))
            source = found[0] if found else source
        converted = serialize_document(sample_document(), 3, "html")
        with patch("functions.ingestion.pdf_to_markdown.convert_pdf", return_value=converted), patch(
                "functions.experiments.export_output.export_markdown_run") as export:
            record = run_markdown(source, replace(SETTINGS, export_enabled=False))
        export.assert_not_called()
        self.assertIs(record["document"], converted)
        self.assertTrue(record["source"]["unchanged"])

    def test_failed_run_has_manifest_without_fake_markdown(self):
        source = SETTINGS.source_dir / "2330" / "2025Q4_2330_Financial_Report.pdf"
        if not source.is_file():
            found = list(SETTINGS.source_dir.rglob("*.pdf"))
            source = found[0] if found else source
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            import pypdfium2 as pdfium
            source = root / 'Financial Statements' / '2025Q4_2330_Financial_Report.pdf'
            source.parent.mkdir()
            with pdfium.PdfDocument.new() as pdf:
                for _ in range(3):
                    pdf.new_page(100, 100).close()
                pdf.save(source)
            with patch("functions.ingestion.pdf_to_markdown.convert_pdf", side_effect=RuntimeError("人工模擬轉換失敗")), patch(
                    "functions.experiments.export_output.export_markdown_run",
                    side_effect=lambda _, stem, record, doc, **kwargs: export_markdown_run(
                        root, stem, record, doc, toc_pdf=kwargs.get('toc_pdf'))):
                record = run_markdown(source, replace(SETTINGS, project_root=root))
            target = Path(record["output_dir"])
            self.assertEqual(record["status"], "failed")
            self.assertFalse((target / "document.md").exists())
            saved = json.loads(next((target / 'Record').glob('*_reocrd')).read_text(encoding="utf-8"))
            self.assertIn("人工模擬", saved["error"])
            self.assertNotIn("document", saved)


if __name__ == "__main__":
    unittest.main()
