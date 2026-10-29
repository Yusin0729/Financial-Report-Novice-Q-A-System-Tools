"""耗時彙整、真實參數API與取消輸出擁有權；不載入模型權重或呼叫API。"""
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from functions.ingestion.timings import wall_timer, finalize_timings, capture_docling_timings
from functions.web_ui.request_settings import request_settings
from functions.experiments.cancelled_run import OutputSession
from functions.experiments.output_ownership import output_observer, exclusive_output
from functions.web_ui.worker import _raw_metrics


class TimingTests(unittest.TestCase):
    def test_profile_accumulates_segments_and_load_not_double_counted(self):
        runtime={'status':'converted_needs_review','settings':{'ocr_enabled':True},
                 'timing_details':{'converter_setup':{'seconds':1,'calls':1},'pipeline_model_load':{'seconds':2,'calls':1}},
                 'ocr_diagnostics':[{'timing':{'ocr_seconds':4,'model_load_seconds':3,'model_load_calls':1}}]}
        profile=NS(timings={'layout':NS(times=[1,2]),'layout_postprocess':NS(times=[.5]),'table_structure':NS(times=[6])})
        capture_docling_timings(runtime,profile)
        capture_docling_timings(runtime,profile)
        summary=finalize_timings(runtime)
        self.assertEqual(summary['stages']['model_load']['seconds'],6)
        self.assertEqual(summary['stages']['ocr']['seconds'],4)
        self.assertEqual(summary['stages']['layout']['seconds'],7)
        self.assertEqual(summary['stages']['table_structure']['seconds'],12)
        self.assertIsNone(summary['stages']['markdown_output']['seconds'])
        self.assertFalse(summary['additive'])
        self.assertEqual(_raw_metrics(runtime,success=True)['stage_timings'],summary)

    def test_failed_and_disabled_are_not_fake_zero(self):
        runtime={'status':'failed','settings':{'ocr_enabled':False}}
        with patch('functions.ingestion.timings.time.perf_counter',side_effect=[2,5]):
            with self.assertRaises(ValueError),wall_timer(runtime,'pipeline_model_load'):
                raise ValueError('test')
        summary=finalize_timings(runtime)['stages']
        self.assertEqual(summary['model_load']['seconds'],3)
        self.assertEqual(summary['model_load']['status'],'partial')
        self.assertEqual(summary['ocr']['status'],'disabled')
        self.assertIsNone(summary['ocr']['seconds'])
        self.assertIsNone(summary['layout']['seconds'])

    def test_converter_uses_installed_mode_api_and_custom_scale(self):
        from functions.ingestion.pdf_to_markdown import create_converter
        base=Settings()
        for mode in ('fast','accurate'):
            settings=request_settings(base,{'ocr':True,'ocr_scale':2.25,'table_mode':mode})
            _,options=create_converter(settings)
            self.assertEqual(options['table_structure_options']['mode'],mode)
            self.assertEqual(options['ocr_options']['scale'],2.25)
            self.assertEqual(options['accelerator_options']['num_threads'],base.pdf_cpu_threads)
            self.assertEqual(options['layout_batch_size'],base.pdf_batch_size)
            self.assertEqual(settings.pdf_manifest()['ocr_scale'],2.25)

    def test_convert_profile_restores_global_and_reuses_models(self):
        from functions.ingestion.pdf_to_markdown import convert_pdf
        from docling.datamodel.settings import settings as global_settings
        from docling.datamodel.base_models import ConversionStatus
        converter=Mock(initialized_pipelines={})
        converter.initialize_pipeline.side_effect=lambda _:converter.initialized_pipelines.update({'cached':True})
        converter.convert.return_value=NS(status=ConversionStatus.SUCCESS,errors=[],document=object(),
                                          timings={'layout':NS(times=[.25]),'table_structure':NS(times=[.5])})
        runtime={}
        original=global_settings.debug.profile_pipeline_timings
        with patch('functions.ingestion.pdf_to_markdown.serialize_document',return_value='document'),patch(
                'functions.integrations.docling_mineru_ocr.collect_diagnostics',return_value=[]):
            for _ in range(2):
                self.assertEqual(convert_pdf(Path('2025Q4_2330_Financial_Report.pdf'),1,Settings(),runtime,
                    converter_bundle=(converter,{}),page_range=(1,1)),'document')
        self.assertEqual(converter.initialize_pipeline.call_count,1)
        self.assertEqual(runtime['docling_timings']['layout']['seconds'],.5)
        self.assertEqual(runtime['timing_details']['markdown_output']['calls'],2)
        self.assertEqual(global_settings.debug.profile_pipeline_timings,original)

    def test_invalid_controls_rejected_and_defaults_preserved(self):
        base=Settings()
        for scale in (0,-1,True,'3',float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                request_settings(base,{'ocr':False,'ocr_scale':scale})
        with self.assertRaises(ValueError):
            request_settings(base,{'ocr':False,'table_mode':'accounting'})
        result=request_settings(base,{'ocr':False})
        self.assertEqual(result.ocr.scale,base.ocr.scale)
        self.assertEqual(result.table_mode,base.table_mode)


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings=Settings(project_root=Path(self.temp.name))
        self.source=self.settings.source_dir/'2025Q4_2330_Financial_Report.pdf'
        self.session=OutputSession(self.settings,'raw',[self.source],'test-run')
        self.batch=self.settings.markdown_output_dir/'Financial_20261024_00-10-00'
        self.batch.mkdir(parents=True)
        self.session.set_raw_batch(str(self.batch))
        self.session.begin(0)

    def test_partial_outputs_removed_and_only_cancel_report_retained(self):
        paths=self.session.active['paths']
        with output_observer(self.session.create):
            with exclusive_output(paths['raw'],'xb') as stream:
                stream.write(b'incomplete')
            with exclusive_output(paths['record'],'x',encoding='utf-8') as stream:
                stream.write('{unfinished')
        result,issues=self.session.cancel()
        self.assertFalse(issues)
        self.assertEqual(result['status'],'cancelled')
        self.assertFalse(paths['raw'].exists())
        self.assertEqual(json.loads(paths['record'].read_text(encoding='utf-8'))['status'],'cancelled')

    def test_existing_and_replaced_files_never_deleted(self):
        raw=self.session.active['paths']['raw']
        with self.assertRaises(ValueError):
            self.session.create(self.settings.project_root/'outside.txt')
        identity=self.session.create(raw)
        raw.write_bytes(b'foreign')
        # 模擬檔案已被其他擁有者替換；不依賴此環境會阻擋的NTFS rename。
        self.session.active['created'][raw]=[identity[0],identity[1]+1]
        _,issues=self.session.cancel()
        self.assertTrue(issues)
        self.assertEqual(raw.read_bytes(),b'foreign')

    def test_failed_record_retry_restored_on_cancel(self):
        self.session=OutputSession(self.settings,'processed',[self.settings.markdown_output_dir/
            'Financial_20261024_00-10-00/2025_2330_raw.md'],'test-run')
        record=self.settings.markdown_processed_output_dir/'Financial_20261024_00-10-00/Record/2025_2330_reocrd'
        record.parent.mkdir(parents=True)
        prior=b'{"status":"failed","old":true}'
        record.write_bytes(prior)
        self.session.set_raw_batch(str(record.parent.parent))
        self.session.begin(0)
        archive=record.with_name(record.name+'.failed-test')
        with output_observer(self.session.create):
            with exclusive_output(archive,'xb') as stream:stream.write(prior)
            record.unlink()
            with exclusive_output(record,'xb') as stream:stream.write(b'{partial')
        _,issues=self.session.cancel()
        self.assertFalse(issues)
        self.assertEqual(record.read_bytes(),prior)
        self.assertFalse(archive.exists())
        self.assertTrue(record.with_name(record.name+'.cancelled-test-run').exists())

    def test_all_markdown_stages_remove_partial_outputs(self):
        for stage,root,role in [('processed',self.settings.markdown_output_dir,'raw'),
                                ('tagged',self.settings.markdown_processed_output_dir,'processed'),
                                ('chunk',self.settings.markdown_tagged_output_dir,'tagged')]:
            with self.subTest(stage=stage):
                source=root/'Financial_20261024_00-10-00'/f'2025_2330_{role}.md'
                session=OutputSession(self.settings,stage,[source],'test-'+stage)
                from functions.web_ui.catalog import STAGES
                output = getattr(self.settings, STAGES[stage][2])/'Financial_20261024_00-10-00'
                session.set_raw_batch(str(output))
                session.begin(0)
                paths=session.active['paths']
                with output_observer(session.create):
                    for key in ('markdown','json'):
                        if key in paths:
                            with exclusive_output(paths[key],'xb') as stream:stream.write(b'partial')
                _,issues=session.cancel()
                self.assertFalse(issues)
                self.assertFalse(paths['markdown'].exists())
                if 'json' in paths:self.assertFalse(paths['json'].exists())
                self.assertEqual(json.loads(paths['record'].read_text(encoding='utf-8'))['status'],'cancelled')

    def test_disabled_output_does_not_create_cancel_record(self):
        session=OutputSession(replace(self.settings,export_enabled=False),'raw',[self.source],'no-export')
        session.begin(0)
        self.assertEqual(session.cancel()[0]['status'],'cancelled')
        self.assertFalse((self.batch/'Record').exists())


if __name__=='__main__':unittest.main()
