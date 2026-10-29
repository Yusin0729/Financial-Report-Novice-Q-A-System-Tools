"""目錄結構／錯誤／輸出隔離測試；全部Gemini回覆為模擬，不連網。"""
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from functions.ingestion.toc_pdf import extract_toc_pdf, validate_toc, parse_response
from functions.integrations.gemini_toc import generate_toc
from main import run_toc, choose_pdf


def fixture():
    return {'pages': [
        {'source_pdf_page': 2, 'classification': 'toc', 'issues': []},
        {'source_pdf_page': 3, 'classification': 'not_toc', 'issues': []}],
        'entries': [
            {'id': 'a', 'parent_id': '', 'title': '九、合併財務報告附註',
             'printed_pages': '', 'note_numbers': '', 'source_pdf_page': 2},
            {'id': 'b', 'parent_id': 'a', 'title': '（一）公司沿革',
             'printed_pages': '15、79～84', 'note_numbers': '一', 'source_pdf_page': 2}]}


def main_fixture():
    data = fixture()
    data['entries'] = [
        {'id': 'a', 'parent_id': '', 'title': '五、合併資產負債表',
         'printed_pages': '8', 'note_numbers': '', 'source_pdf_page': 2},
        {'id': 'b', 'parent_id': '', 'title': '九、合併財務報告附註',
         'printed_pages': '15、79～84', 'note_numbers': '', 'source_pdf_page': 2}]
    return data


def response(value=None, reason='STOP'):
    return {'candidates': [{'finishReason': reason, 'content': {'parts': [
        {'text': json.dumps(value if value is not None else main_fixture(), ensure_ascii=False)}]}}],
        'usageMetadata': {'promptTokenCount': 123, 'candidatesTokenCount': 456}}


def make_pdf(count=4):
    import pypdfium2 as pdfium
    with pdfium.PdfDocument.new() as pdf:
        for index in range(count):
            page = pdf.new_page(300 + index * 10, 400 + index * 10)
            page.close()
        stream = BytesIO()
        pdf.save(stream)
    return stream.getvalue()


class TocTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(project_root=Path(self.temp.name))
        self.settings.source_dir.mkdir()
        self.source = self.settings.source_dir / '2025Q4_2330_Financial_Report.pdf'
        self.source.write_bytes(make_pdf())
        self.pdf = extract_toc_pdf(self.source)

    def test_extract_physical_pages_without_changing_source(self):
        import pypdfium2 as pdfium
        self.assertEqual(self.pdf.source_pages, (2, 3))
        self.assertEqual(self.pdf.source_page_count, 4)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.pdf.source_sha256)
        with pdfium.PdfDocument(self.pdf.data) as pdf:
            self.assertEqual(len(pdf), 2)
            self.assertEqual(pdf.get_page_size(0), (310., 410.))
            self.assertEqual(pdf.get_page_size(1), (320., 420.))

    def test_insufficient_or_other_pages_rejected(self):
        self.source.write_bytes(make_pdf(2))
        with self.assertRaises(ValueError): extract_toc_pdf(self.source)
        with self.assertRaises(ValueError): extract_toc_pdf(self.source, (1, 2))

    def test_valid_schema_preserves_raw_page_strings(self):
        result = parse_response(response(), self.pdf)
        self.assertEqual(result.status, 'extracted_needs_review')
        self.assertEqual(result.toc['entries'][0]['printed_pages'], '8')
        self.assertEqual(result.toc['entries'][1]['printed_pages'], '15、79～84')
        self.assertNotIn('notes_range', result.toc)
        self.assertEqual(result.toc['extraction_mode'], 'main_titles')
        self.assertEqual(result.toc['schema_version'], 'financial-toc/2.0')

    def test_api_response_rejects_nested_items_and_note_numbers(self):
        with self.assertRaisesRegex(ValueError, '僅允許目錄大標'):
            parse_response(response(fixture()), self.pdf)
        value = main_fixture()
        value['entries'][0]['note_numbers'] = '一'
        with self.assertRaisesRegex(ValueError, '僅允許目錄大標'):
            parse_response(response(value), self.pdf)

    def test_missing_extra_fields_types_and_duplicate_pages_rejected(self):
        cases = []
        value=fixture(); del value['entries'][0]['note_numbers']; cases.append(value)
        value=fixture(); value['notes_range']=[15,85]; cases.append(value)
        value=fixture(); value['entries'][0]['source_pdf_page']=True; cases.append(value)
        value=fixture(); value['pages'][1]['source_pdf_page']=2; cases.append(value)
        value=fixture(); value['entries'][0]['printed_pages']=15; cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError): validate_toc(value)

    def test_hierarchy_duplicate_ids_and_not_toc_entries_rejected(self):
        for key, value in [('parent_id','missing'),('id','a'),('title',''),('source_pdf_page',3)]:
            data=fixture(); data['entries'][1][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_toc(data)

    def test_empty_toc_not_success(self):
        data=fixture(); data['entries']=[]
        with self.assertRaises(ValueError): validate_toc(data)
        data['pages'][0]['classification']='not_toc'
        self.assertEqual(validate_toc(data), 'no_toc_found')

    def test_unreadable_explicitly_incomplete(self):
        data=fixture(); data['pages'][1]['classification']='unreadable'
        with self.assertRaises(ValueError): validate_toc(data)
        data['pages'][1]['issues']=['影像模糊']
        self.assertEqual(validate_toc(data),'incomplete_needs_review')

    def test_truncated_blocked_missing_and_invalid_json_rejected(self):
        cases=[response(reason='MAX_TOKENS'),response(reason='SAFETY'),{},
               {'promptFeedback':{'blockReason':'SAFETY'}}]
        bad=response();bad['candidates'][0]['content']['parts'][0]['text']='{';cases.append(bad)
        empty=response();empty['candidates'][0]['content']['parts']=[];cases.append(empty)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError): parse_response(value,self.pdf)

    def test_no_key_does_not_extract_upload_or_write(self):
        with patch.dict('os.environ',{},clear=True), patch('functions.ingestion.toc_pdf.extract_toc_pdf') as extract:
            with self.assertRaisesRegex(ValueError,'尚未設定'): run_toc(self.source,self.settings)
            extract.assert_not_called()
        self.assertFalse(self.settings.toc_output_dir.exists())

    def test_request_only_contains_extracted_pdf_and_confirmed_parameters(self):
        reply=MagicMock();reply.__enter__.return_value.read.return_value=json.dumps(response()).encode()
        opener=MagicMock();opener.open.return_value=reply
        with patch.dict('os.environ',{'GEMINI_API_KEY':'FAKE_TEST_KEY'}), \
             patch('functions.integrations.gemini_toc.build_opener',return_value=opener):
            generate_toc(self.pdf,self.settings.toc)
        request=opener.open.call_args.args[0]
        payload=json.loads(request.data)
        inline=payload['contents'][0]['parts'][0]['inlineData']
        self.assertEqual(base64.b64decode(inline['data']),self.pdf.data)
        self.assertNotEqual(base64.b64decode(inline['data']),self.source.read_bytes())
        self.assertEqual(payload['generationConfig']['maxOutputTokens'],8192)
        self.assertEqual(opener.open.call_args.kwargs['timeout'],120)
        self.assertNotIn('FAKE_TEST_KEY',request.full_url)
        self.assertEqual(opener.open.call_count,1)
        properties = payload['generationConfig']['responseJsonSchema']['properties']['entries']['items']['properties']
        self.assertEqual(properties['parent_id']['enum'], [''])
        self.assertEqual(properties['note_numbers']['enum'], [''])
        prompt = payload['contents'][0]['parts'][1]['text']
        self.assertIn('只輸出目錄頂層大標 MAIN_TITLE', prompt)
        self.assertIn('聯集', prompt)

    def test_http_timeout_and_connection_errors_not_retried(self):
        errors=[HTTPError('url',429,'rate',{},None),TimeoutError(),URLError('offline')]
        for error in errors:
            opener=MagicMock();opener.open.side_effect=error
            with patch.dict('os.environ',{'GEMINI_API_KEY':'FAKE_TEST_KEY'}), \
                 patch('functions.integrations.gemini_toc.build_opener',return_value=opener), \
                 self.assertRaises(RuntimeError): generate_toc(self.pdf,self.settings.toc)
            self.assertEqual(opener.open.call_count,1)

    def test_503_retry_delays_bounded_and_same_pdf_sent(self):
        for failures in (0, 1, 3, 4):
            with self.subTest(failures=failures):
                reply = MagicMock()
                reply.__enter__.return_value.read.return_value = json.dumps(response()).encode()
                opener = MagicMock()
                opener.open.side_effect = [HTTPError('url', 503, 'busy', {}, None) for _ in range(failures)] + [reply]
                attempts = []
                with patch.dict('os.environ', {'GEMINI_API_KEY': 'FAKE_TEST_KEY'}), \
                     patch('functions.integrations.gemini_toc.build_opener', return_value=opener), \
                     patch('functions.integrations.gemini_toc.time.sleep') as sleep:
                    if failures == 4:
                        with self.assertRaisesRegex(RuntimeError, '共嘗試4次'):
                            generate_toc(self.pdf, self.settings.toc, attempt_log=attempts)
                    else:
                        self.assertEqual(generate_toc(self.pdf, self.settings.toc, attempt_log=attempts), response())
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 10, 20][:failures])
                self.assertEqual(opener.open.call_count, min(failures + 1, 4))
                requests = [c.args[0].data for c in opener.open.call_args_list]
                self.assertTrue(all(data == requests[0] for data in requests))
                self.assertEqual(len(attempts), opener.open.call_count)
                self.assertEqual(attempts[-1]['status'], 'http_error' if failures == 4 else 'response_received')
                self.assertNotIn('FAKE_TEST_KEY', json.dumps(attempts))

    def test_retry_stops_on_non503_or_user_interrupt(self):
        for stop in ('429', 'interrupt'):
            opener = MagicMock()
            opener.open.side_effect = [HTTPError('url', 503, 'busy', {}, None),
                                      HTTPError('url', 429, 'rate', {}, None)]
            attempts = []
            with patch.dict('os.environ', {'GEMINI_API_KEY': 'FAKE_TEST_KEY'}), \
                 patch('functions.integrations.gemini_toc.build_opener', return_value=opener), \
                 patch('functions.integrations.gemini_toc.time.sleep',
                       side_effect=KeyboardInterrupt if stop == 'interrupt' else None) as sleep:
                with self.assertRaises(KeyboardInterrupt if stop == 'interrupt' else RuntimeError):
                    generate_toc(self.pdf, self.settings.toc, attempt_log=attempts)
            self.assertEqual(opener.open.call_count, 1 if stop == 'interrupt' else 2)
            sleep.assert_called_once_with(5)
            if stop == 'interrupt':
                self.assertEqual(attempts[0]['wait_status'], 'interrupted')

    def test_503_retries_can_be_disabled(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError('url', 503, 'busy', {}, None)
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'FAKE_TEST_KEY'}), \
             patch('functions.integrations.gemini_toc.build_opener', return_value=opener), \
             patch('functions.integrations.gemini_toc.time.sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, '共嘗試1次'):
                generate_toc(self.pdf, replace(self.settings.toc, retries=0))
        opener.open.assert_called_once()
        sleep.assert_not_called()

    def test_disabled_export_returns_memory_and_creates_no_directory(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'FAKE_TEST_KEY'}), \
             patch('functions.integrations.gemini_toc.generate_toc',return_value=response()):
            record=run_toc(self.source,replace(self.settings,export_enabled=False))
        self.assertIsNone(record['output_dir'])
        self.assertEqual(record['result'].status,'extracted_needs_review')
        self.assertFalse(self.settings.toc_output_dir.exists())

    def test_export_names_source_mapping_usage_and_no_overwrite(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'FAKE_TEST_KEY'}), \
             patch('functions.integrations.gemini_toc.generate_toc',return_value=response()):
            records=[run_toc(self.source,self.settings) for _ in range(2)]
        self.assertNotEqual(records[0]['output_dir'],records[1]['output_dir'])
        root=Path(records[0]['output_dir'])
        self.assertTrue((root/'2025_2330_toc.json').exists())
        manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['page_mapping'][0],{'extracted_page':1,'source_pdf_page':2})
        self.assertEqual(manifest['usage']['promptTokenCount'],123)
        self.assertNotIn('FAKE_TEST_KEY',(root/'manifest.json').read_text(encoding='utf-8'))

    def test_failed_validation_exports_diagnostics_not_valid_toc(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'FAKE_TEST_KEY'}), \
             patch('functions.integrations.gemini_toc.generate_toc',return_value=response(reason='MAX_TOKENS')):
            with self.assertRaises(ValueError): run_toc(self.source,self.settings)
        root=next(self.settings.toc_output_dir.glob('*/*'))
        self.assertTrue((root/'raw_response.json').exists())
        self.assertFalse((root/'2025_2330_toc.json').exists())
        self.assertEqual(json.loads((root/'manifest.json').read_text(encoding='utf-8'))['status'],'failed')

    def test_toc_selection_rejects_batch(self):
        with patch('builtins.input',side_effect=['A','1,1','1']):
            self.assertEqual(choose_pdf(self.settings,single=True),[self.source])

    def test_cli_toc_no_export_dispatch(self):
        import main
        with patch('sys.argv',['main.py','--toc-pdf',str(self.source),'--no-export']), \
             patch.object(main,'run_toc',return_value={'status':'extracted_needs_review'}) as run:
            self.assertEqual(main.main(),0)
        self.assertEqual(run.call_args.args[0],self.source)
        self.assertFalse(run.call_args.args[1].export_enabled)

    def test_menu5_dispatches_single_pdf_without_conversion(self):
        import main
        with patch('sys.argv',['main.py']),patch('builtins.input',side_effect=['5','0']), \
             patch.object(main,'choose_pdf',return_value=[self.source]) as choose, \
             patch.object(main,'run_toc') as run,patch.object(main,'run_markdown') as convert:
            self.assertEqual(main.main(),0)
        self.assertTrue(choose.call_args.kwargs['single'])
        run.assert_called_once()
        convert.assert_not_called()

    def test_source_change_during_request_rejected(self):
        def mutate(*args, **kwargs):
            self.source.write_bytes(make_pdf(5))
            return response()
        with patch.dict('os.environ',{'GEMINI_API_KEY':'FAKE_TEST_KEY'}), \
             patch('functions.integrations.gemini_toc.generate_toc',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'來源PDF在處理期間變更'):
                run_toc(self.source,replace(self.settings,export_enabled=False))


if __name__=='__main__': unittest.main()
