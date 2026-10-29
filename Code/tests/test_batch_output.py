"""批次路徑、真實本機抽頁與模擬轉換串接；不載入模型或外傳。"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from config.settings import SETTINGS
from functions.experiments.export_output import create_markdown_batch
from functions.markdown_processing.load_source import is_selectable_markdown, load_source
from test_markdown import sample_document
from functions.ingestion.pdf_to_markdown import serialize_document


class BatchOutputTests(unittest.TestCase):
    def test_same_report_in_two_batches_has_independent_records_despite_legacy_file(self):
        import pypdfium2 as pdfium
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(SETTINGS, project_root=Path(tmp))
            settings.source_dir.mkdir()
            source = settings.source_dir / '2025Q4_2330_Financial_Report.pdf'
            with pdfium.PdfDocument.new() as pdf:
                for _ in range(3):
                    pdf.new_page(100, 100).close()
                pdf.save(source)
            legacy = settings.markdown_output_dir / 'Record' / '2025_2330_reocrd'
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b'legacy record unchanged')
            doc = serialize_document(sample_document(), 3, 'html', pdf_identity=('2025', '2330'))
            def convert(source, count, settings, record, progress):
                record['ocr_diagnostics'] = []
                return doc
            batches = [create_markdown_batch(settings.markdown_output_dir,
                       now=datetime(2026, 10, 22, 8, 1, second, tzinfo=timezone.utc)) for second in (35, 36)]
            with patch('functions.ingestion.pdf_to_markdown.convert_pdf', side_effect=convert) as convert_mock:
                for batch in batches:
                    result = main.run_markdown(source, settings, batch_dir=batch)
                    self.assertEqual(result['status'], 'converted_needs_review')
                    path = batch / 'Record' / '2025_2330_reocrd'
                    saved = json.loads(path.read_text(encoding='utf-8'))
                    self.assertEqual(saved['batch_dir'], str(batch))
                    self.assertEqual(saved['output_layout'], 'financial-batch/1.1')
                    self.assertTrue(path.with_name(path.name + '.ocr').is_file())
                with self.assertRaises(FileExistsError):
                    main.run_markdown(source, settings, batch_dir=batches[0])
                self.assertEqual(convert_mock.call_count, 2)
            self.assertEqual(legacy.read_bytes(), b'legacy record unchanged')

    def test_menu_reuses_batch_and_interrupt_stops_remaining(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), tempfile.TemporaryDirectory() as tmp:
                settings = replace(SETTINGS, project_root=Path(tmp))
                files = [settings.source_dir / f'2025Q4_{stock}_Financial_Report.pdf' for stock in ('2330', '2317')]
                status = 'interrupted' if interrupted else 'converted_needs_review'
                with patch.object(main, 'SETTINGS', settings), patch.object(sys, 'argv', ['main.py']), patch(
                        'builtins.input', side_effect=['1', '0']), patch('main.choose_pdf', return_value=files), patch(
                        'main.run_markdown', return_value={'status': status}) as run:
                    self.assertEqual(main.main(), 0)
                self.assertEqual(run.call_count, 1 if interrupted else 2)
                batches = list(settings.markdown_output_dir.glob('Financial_*'))
                self.assertEqual(len(batches), 1)
                self.assertTrue(all(call.kwargs['batch_dir'] == batches[0] for call in run.call_args_list))

    def test_taiwan_time_instead_of_sequence_and_legacy_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / 'old_docling_run'
            legacy.mkdir()
            date = datetime(2026, 10, 21, 15, 59, tzinfo=timezone.utc)
            first = create_markdown_batch(root, now=date)
            self.assertEqual(first.name, 'Financial_raw_20261021_23-59-00')
            (first / 'keep.txt').write_text('existing', encoding='utf-8')
            with self.assertRaisesRegex(FileExistsError, '同一秒'):
                create_markdown_batch(root, now=date)
            self.assertEqual((first / 'keep.txt').read_text(encoding='utf-8'), 'existing')
            self.assertEqual(create_markdown_batch(root, now=date.replace(second=1)).name,
                             'Financial_raw_20261021_23-59-01')
            later = datetime(2026, 10, 21, 16, 1, tzinfo=timezone.utc)
            self.assertEqual(create_markdown_batch(root, now=later).name, 'Financial_raw_20261022_00-01-00')
            self.assertTrue(legacy.is_dir())

    def test_selectors_accept_new_time_and_old_sequence_names(self):
        from functions.markdown_processing.process_batch import list_raw_batches
        from functions.markdown_processing.tag_batch import list_processed_batches
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(SETTINGS, project_root=Path(tmp))
            for root in (settings.markdown_output_dir, settings.markdown_processed_output_dir):
                for name in ('Financial_20261021_001', 'Financial_20261022_16-01-35',
                             'Financial_raw_20261025_16-01-30',
                             'Financial_20261022_25-61-70', 'Record'):
                    (root / name).mkdir(parents=True)
            expected = ['Financial_20261021_001', 'Financial_20261022_16-01-35',
                        'Financial_raw_20261025_16-01-30']
            self.assertEqual([p.name for p in list_raw_batches(settings)], expected)
            self.assertEqual([p.name for p in list_processed_batches(settings)], expected)

    def test_batch_real_pdf_extraction_mock_conversion_no_network(self):
        import pypdfium2 as pdfium
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(SETTINGS, project_root=Path(tmp))
            settings.source_dir.mkdir()
            batch = create_markdown_batch(settings.markdown_output_dir)
            document = serialize_document(sample_document(), 3, 'html')
            def convert(source, count, settings, record, progress):
                record['ocr_diagnostics'] = []
                return document
            with patch('functions.ingestion.pdf_to_markdown.convert_pdf', side_effect=convert), patch(
                    'functions.integrations.gemini_toc.generate_toc', side_effect=AssertionError('禁止外傳')) as api:
                for stock in ('2330', '2317'):
                    source = settings.source_dir / f'2025Q4_{stock}_Financial_Report.pdf'
                    with pdfium.PdfDocument.new() as pdf:
                        for width in (101, 202, 303):
                            pdf.new_page(width, 400).close()
                        pdf.save(source)
                    before = source.read_bytes()
                    result = main.run_markdown(source, settings, batch_dir=batch)
                    self.assertEqual(result['status'], 'converted_needs_review')
                    self.assertEqual(source.read_bytes(), before)
                    raw = batch / f'2025_{stock}_raw.md'
                    self.assertEqual(raw.read_bytes(), document.markdown.encode('utf-8'))
                    self.assertTrue(is_selectable_markdown(raw))
                    record_path = batch / 'Record' / f'2025_{stock}_reocrd'
                    saved = json.loads(record_path.read_text(encoding='utf-8'))
                    self.assertEqual(saved['table_source_pages'], [2, 3])
                    self.assertTrue(record_path.with_name(record_path.name + '.ocr').is_file())
                    with pdfium.PdfDocument(batch / 'Financial_Table' / f'2025_{stock}_table.pdf') as pdf:
                        self.assertEqual(len(pdf), 2)
                        self.assertEqual([pdf[i].get_width() for i in range(2)], [202, 303])
                api.assert_not_called()
                with self.assertRaises(FileExistsError):
                    main.run_markdown(source, settings, batch_dir=batch)
            self.assertEqual(len(list(batch.glob('*.md'))), 2)
            self.assertFalse(list(batch.glob('*_document.md')))
            old_raw = batch / '2024_2330_raw.md'
            old_raw.write_text('old unmarked text', encoding='utf-8')
            self.assertFalse(is_selectable_markdown(old_raw))
            old_doc = batch / '2024_2330_document.md'
            old_doc.write_text('legacy', encoding='utf-8')
            self.assertTrue(is_selectable_markdown(old_doc))
            self.assertEqual(load_source(old_doc)[1], 'legacy')


if __name__ == '__main__':
    unittest.main()
