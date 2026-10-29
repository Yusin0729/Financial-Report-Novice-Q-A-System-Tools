"""本機chunk規則與完整表格；所有資料為合成，不使用API。"""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.chunking import ChunkSettings
from config.settings import SETTINGS
from functions.chunking.chunks import chunk_tagged_legacy as chunk_tagged, validate_chunk_document, visible_units
from functions.chunking.batch import chunk_tagged_batch
from functions.markdown_processing.comment_tagging import tag_comments
from schemas import TaggingMetadata

IDENTITY = ('2025', '2330')


def page(number):
    return f'<!-- Page: 2330_2025_P{number} -->\n'


def tagged(raw):
    return tag_comments(raw, None, TaggingMetadata(report_year='2025', stock_code='2330')).markdown


def convert(text, config=ChunkSettings()):
    return chunk_tagged(text, identity=IDENTITY, source_sha256=hashlib.sha256(text.encode()).hexdigest(), config=config)


class ChunkCoreTests(unittest.TestCase):
    def test_legacy_page_snapshots_and_empty_hd_are_context_not_new_sections(self):
        source = ('<page_start>\n' + page(15) + '<!-- MAIN_TITLE: 附錄 -->\n<hd2></hd2>\n'
                  '<hd2>一、公司沿革</hd2>\n<hd3></hd3>\n<hd3>(一) 基礎</hd3>\n'
                  '<content_start>\n前頁正文\n</content_end>\n<page_end>\n<page_start>\n' + page(16) +
                  '<!-- MAIN_TITLE: 附錄 -->\n<hd2>一、公司沿革</hd2>\n'
                  '<content_start>\n後頁正文\n</content_end>\n<hd4>1. 方法</hd4>\n'
                  '<content_start>\n細節正文\n</content_end>\n<page_end>\n')
        result = chunk_tagged(source, identity=IDENTITY, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                              legacy_page_snapshots=True, legacy_empty_hd=True)
        self.assertEqual(len(result.document['chunks']), 1)
        chunk = result.document['chunks'][0]
        self.assertEqual(chunk['page'], [15, 16])
        self.assertEqual(chunk['title']['heading']['children'][0]['children'][0]['text'], '1. 方法')
        self.assertNotIn('<hd3></hd3>', result.markdown)
        self.assertEqual(result.markdown.count('<!-- Sub_Section: 一、公司沿革 -->'), 1)

    def test_chunk_merges_separate_tagged_table_blocks_using_either_marker(self):
        one = '<table><tr><td>甲</td></tr></table>\n'
        two = '<table><tr><td>乙</td></tr></table>\n'
        source = (page(15) + '<page_start>\n<hd2>一、公司沿革</hd2>\n<table_start>\n' + one +
                  '<table_end>\n<content_start>\n承 前 頁\n</content_end>\n<page_end>\n' + page(16) +
                  '<page_start>\n<table_start>\n' + two + '<table_end>\n<page_end>\n')
        result = convert(source)
        self.assertEqual(len(result.document['chunks']), 2)
        table = result.document['parents'][0]
        self.assertEqual(table['page'], [15, 16])
        self.assertIn(one, table['content'])
        self.assertIn(two, table['content'])
        self.assertNotIn('<content_start>', table['content'])
        self.assertNotIn('<table_end>', table['content'])
        self.assertEqual(''.join(source[s['start']:s['end']] for s in table['source_spans']), table['content'])

    def test_keeps_prefix_merges_small_subheadings_and_forces_hd2(self):
        source = tagged(page(1) + '不納入的會計師報告\n' + page(15) +
                        '## 一 、 公司沿革\n公司正文\n## (一) 子標甲\n甲正文\n'
                        '## (二) 子標乙\n乙正文\n## 二、會計政策\n政策正文\n')
        result = convert(source)
        chunks = result.document['chunks']
        self.assertEqual(len(chunks), 3)
        self.assertIn('不納入的會計師報告', result.markdown)
        self.assertIsNone(chunks[0]['title']['heading'])
        chunks = chunks[1:]
        self.assertEqual(chunks[0]['page'], [15])
        self.assertEqual(chunks[0]['years'], [2025])
        self.assertEqual(chunks[0]['doc_id'], '2025Q4_2330_Financial_Report')
        self.assertTrue(chunks[0]['chunk_id'].endswith('__c00002'))
        self.assertEqual(chunks[0]['data_tags'], [])
        root = chunks[0]['title']['heading']
        self.assertEqual(root['text'], '一 、 公司沿革')
        self.assertEqual([c['text'] for c in root['children']], ['(一) 子標甲', '(二) 子標乙'])
        body = result.markdown.split('<content_start>')[2].split('</content_end>')[0]
        self.assertIn('<hd3>(一) 子標甲</hd3>', body)
        self.assertLess(body.index('公司正文'), body.index('<hd3>(一) 子標甲</hd3>'))
        self.assertNotIn('<hd2>', body)
        self.assertEqual(convert(source).document, result.document)

    def test_target_waits_for_content_end_without_truncating(self):
        source = tagged(page(35) + '## 一、公司沿革\n' + '甲' * 1100 + '\n## (一) 子標\n乙\n')
        chunks = convert(source).document['chunks']
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]['body_char_count'], 1100)
        self.assertEqual(chunks[0]['cut_reason'], 'target_then_content_end')
        self.assertIn('甲' * 1100, chunks[0]['content'])

    def test_p35_limit_waits_until_first_chinese_period_from_p37(self):
        source = tagged(page(35) + '## 一、公司沿革\n## (一) 基礎\n' + '甲' * 1000 + '\n' +
                        page(36) + '前頁。仍應保留\n' + page(37) + '金額1.25後的句號。尾段\n')
        chunks = convert(source).document['chunks']
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]['cut_reason'], 'grace_page_sentence')
        self.assertEqual(chunks[0]['page'], [35, 36, 37])
        self.assertEqual(chunks[1]['page'], [37])
        self.assertTrue(chunks[0]['content'].endswith('金額1.25後的句號。'))
        self.assertIn('前頁。仍應保留', chunks[0]['content'])
        self.assertIn('尾段', chunks[1]['content'])
        self.assertEqual(chunks[1]['title']['heading']['children'][0]['text'], '(一) 基礎')
        second_markdown = convert(source).markdown.split(f'<!-- chunk_id: {chunks[1]["chunk_id"]} -->')[1]
        self.assertIn('<content_start>\n<hd3>(一) 基礎</hd3>\n', second_markdown)

    def test_new_deeper_heading_gets_inherited_parent_without_duplicate_child(self):
        source = tagged(page(15) + '## 一、公司沿革\n## (一) 基礎\n' + '甲'*1000 +
                        '\n## 1. 新方法\n新方法正文\n')
        result = convert(source)
        chunks = result.document['chunks']
        self.assertEqual(len(chunks), 2)
        second = result.markdown.split(f'<!-- chunk_id: {chunks[1]["chunk_id"]} -->')[1]
        self.assertIn('<content_start>\n<hd3>(一) 基礎</hd3>\n<hd4>1. 新方法</hd4>', second)
        self.assertEqual(second.count('<hd4>1. 新方法</hd4>'), 1)

    def test_content_end_on_p36_takes_priority_over_p37_grace(self):
        source = tagged(page(35) + '## 一、公司沿革\n' + '甲' * 1000 + '\n' +
                        page(36) + '仍同一段\n## (一) 新標題\n新正文\n' + page(37) + '後文。\n')
        chunks = convert(source).document['chunks']
        self.assertEqual(chunks[0]['cut_reason'], 'target_then_content_end')
        self.assertEqual(chunks[0]['page'], [35, 36])

    def test_without_chinese_period_waits_for_hd2_or_eof(self):
        source = tagged(page(35) + '## 一、公司沿革\n' + '甲'*1000 + '\n' +
                        page(37) + '數字1.25仍不切\n' + page(38) + '最後正文\n')
        chunks = convert(source).document['chunks']
        self.assertEqual(len(chunks), 1)
        self.assertIn('最後正文', chunks[0]['content'])
        self.assertEqual(chunks[0]['cut_reason'], 'target_then_content_end')

    def test_counts_only_body_not_headings_whitespace_or_html_markup(self):
        source = tagged(page(15) + '## 一、公司沿革\n## (一) 很長的標題不算字數\n'
                        '<b>甲 &amp; 乙</b> 123。\n\t\n')
        chunk = convert(source).document['chunks'][0]
        self.assertEqual(chunk['body_char_count'], 7)
        self.assertIn('<b>甲 &amp; 乙</b> 123。', chunk['content'])
        self.assertEqual(sum(weight for _, weight, _ in visible_units('甲 < 3。')), 4)

    def test_multpage_table_never_cut_and_exact_html_and_gap_retained(self):
        tables = [f'<table><tr><td>{"甲"*1200}{n}</td></tr></table>' for n in range(3)]
        raw = page(15) + '## 一、公司沿革\n前文\n' + tables[0] + '\n接 次 頁\n' + page(16)
        raw += tables[1] + '\n承\u3000前\u3000頁\n' + page(17) + tables[2] + '\n後文\n'
        source = tagged(raw)
        result = convert(source)
        chunks = result.document['chunks']
        table = result.document['parents'][0]
        self.assertEqual([c['content_type'] for c in chunks], ['text', 'table', 'table', 'table', 'text'])
        self.assertEqual(table['page'], [15, 16, 17])
        for original in tables + ['接 次 頁', '承\u3000前\u3000頁']:
            self.assertIn(original, table['content'])
            self.assertIn(original, result.markdown)
        span = table['source_spans'][0]
        self.assertEqual(source[span['start']:span['end']], table['content'])

    def test_wrong_identity_and_malformed_boundaries_rejected(self):
        source = tagged(page(15) + '## 一、公司沿革\n正文\n')
        cases = [source.replace('2330_2025', '2317_2025'),
                 source.replace('</content_end>', ''), source.replace('<page_end>', ''),
                 source.replace('<!-- Page: 2330_2025_P15 -->', '<!-- PDF_PAGE: 15 -->')]
        for text in cases:
            with self.subTest(text=text[:70]), self.assertRaises(ValueError):
                convert(text)

    def test_table_only_section_has_root_path_without_empty_text_chunk(self):
        source = tagged(page(15) + '## 一、公司沿革\n## (一) 子標\n<table><tr><td>數值</td></tr></table>\n')
        result = convert(source)
        chunks = result.document['chunks']
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['content_type'], 'table')
        self.assertEqual(chunks[0]['title']['heading']['children'][0]['text'], '(一) 子標')
        self.assertIn('<hd3>(一) 子標</hd3>\n<table_start>', result.markdown)
        self.assertNotIn('<hd3>', chunks[0]['content'])

    def test_unclassified_heading_before_table_is_preserved_without_counting_as_body(self):
        source = tagged(page(15) + '## 一、公司沿革\n## 表格相關主要條件如下：\n'
                        '<table><tr><td>數值</td></tr></table>\n')
        result = convert(source)
        self.assertIn('<content_direction>表格相關主要條件如下：</content_direction>', result.markdown)
        text_chunk = next(c for c in result.document['chunks'] if c['content_type'] == 'text')
        self.assertEqual(text_chunk['body_char_count'], 0)

    def test_schema_rejects_bad_pages(self):
        doc = convert(tagged(page(15) + '## 一、公司沿革\n正文\n')).document
        doc['chunks'][0]['page'] = [16, 15]
        with self.assertRaises(ValueError):
            validate_chunk_document(doc)


class ChunkBatchTests(unittest.TestCase):
    def setup_batch(self, folder, stock='2330'):
        settings = replace(SETTINGS, project_root=Path(folder))
        batch = settings.markdown_tagged_output_dir / 'Financial_20261022_16-01-35'
        (batch / 'Record').mkdir(parents=True, exist_ok=True)
        text = tagged(page(15) + '## 一、公司沿革\n正文\n').replace('2330_2025', f'{stock}_2025')
        source = batch / f'2025_{stock}_tagged.md'
        source.write_bytes(text.encode('utf-8'))
        origin = {'batch': batch.name, 'status': 'tagged_temporary_fallback_needs_review',
                  'version': 'markdown-comment-tagging/2.8', 'temporary_fallback': True,
                  'output_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        (batch / 'Record' / f'2025_{stock}_reocrd').write_text(json.dumps(origin), encoding='utf-8')
        return settings, batch, source

    def test_outputs_pair_record_and_no_api_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, source = self.setup_batch(tmp)
            before = source.read_bytes()
            with patch('functions.integrations.gemini_toc.generate_toc', side_effect=AssertionError('不得呼叫API')) as api:
                result = chunk_tagged_batch(batch, settings)[0]
                api.assert_not_called()
            self.assertEqual(result['status'], 'chunked_needs_review')
            target = Path(result['output_dir'])
            doc = json.loads((target / '2025_2330_chunk_text-full_table-full.json').read_text(encoding='utf-8'))
            validate_chunk_document(doc)
            self.assertIn(doc['chunks'][0]['chunk_id'], (target / '2025_2330_chunk_text-full_table-full.md').read_text(encoding='utf-8'))
            record = json.loads((target / 'Record/2025_2330_text-full_table-full_reocrd').read_text(encoding='utf-8'))
            self.assertEqual(set(record['outputs']), {'markdown', 'json'})
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                chunk_tagged_batch(batch, settings, output_batch=target.parent)

    def test_record_mismatch_is_audit_only_and_other_headings_are_allowed(self):
        for mode in ('old', 'hash', 'heading'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                settings, batch, source = self.setup_batch(tmp)
                origin_path = batch / 'Record/2025_2330_reocrd'
                origin = json.loads(origin_path.read_text(encoding='utf-8'))
                if mode == 'old':
                    origin['version'] = 'markdown-comment-tagging/2.1'
                elif mode == 'hash':
                    origin['output_sha256'] = 'b' * 64
                else:
                    source.write_text(source.read_text(encoding='utf-8').replace('公司沿革', '其他'), encoding='utf-8')
                    origin['output_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
                origin_path.write_text(json.dumps(origin), encoding='utf-8')
                result = chunk_tagged_batch(batch, settings)[0]
                expected = 'chunked_needs_review'
                self.assertEqual(result['status'], expected)
                self.assertEqual(bool(list(settings.markdown_chunk_output_dir.rglob('*_chunk*.json'))),
                                 expected == 'chunked_needs_review')
                if mode == 'hash':
                    self.assertIn('雜湊', result['source_record_issue'])

    def test_disabled_export_returns_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, _ = self.setup_batch(tmp)
            result = chunk_tagged_batch(batch, replace(settings, export_enabled=False))[0]
            self.assertEqual(result['status'], 'chunked_needs_review')
            self.assertIsNotNone(result['result'])
            self.assertFalse(settings.markdown_chunk_output_dir.exists())

    def test_failed_document_continues_and_interrupt_stops_batch(self):
        for mode in ('failed', 'interrupted'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                settings, batch, first = self.setup_batch(tmp, stock='2317')
                self.setup_batch(tmp, stock='2330')
                if mode == 'failed':
                    first.write_text('內容被改動', encoding='utf-8')
                    records = chunk_tagged_batch(batch, settings)
                    self.assertEqual([r['status'] for r in records], ['needs_confirmation', 'chunked_needs_review'])
                else:
                    with patch('functions.chunking.batch.chunk_tagged', side_effect=KeyboardInterrupt):
                        records = chunk_tagged_batch(batch, settings)
                    self.assertEqual([r['status'] for r in records], ['interrupted'])
                self.assertFalse((settings.markdown_chunk_output_dir / batch.name / settings.chunking.mode / '2025_2317_chunk_text-full_table-full.json').exists())

    def test_partial_pair_write_failure_removes_only_new_files_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch, source = self.setup_batch(tmp)
            original_open = Path.open
            def fail_json(path, *args, **kwargs):
                if path.name.endswith('_chunk_text-full_table-full.json') and args and args[0] == 'xb':
                    raise OSError('模擬磁碟寫入失敗')
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', fail_json):
                record = chunk_tagged_batch(batch, settings)[0]
            self.assertEqual(record['status'], 'failed')
            self.assertTrue(source.exists())
            self.assertFalse(list(settings.markdown_chunk_output_dir.rglob('*_chunk*.md')))
            self.assertFalse(list(settings.markdown_chunk_output_dir.rglob('*_chunk*.json')))
            out_record = Path(record['output_dir']) / 'Record/2025_2330_text-full_table-full_reocrd'
            self.assertEqual(json.loads(out_record.read_text(encoding='utf-8'))['status'], 'failed')

    def test_cli_and_menu6_dispatch(self):
        import main
        for mode in ('cli', 'menu'):
            with self.subTest(mode=mode):
                argv = ['main.py', '--chunk-batch', 'Output/markdown_tagged/Financial_20261022_16-01-35', '--no-export'] if mode == 'cli' else ['main.py']
                with patch('sys.argv', argv), patch('builtins.input', side_effect=['6', '0']), \
                     patch.object(main, 'choose_tagged_batch', return_value=Path('batch')), \
                     patch.object(main, 'chunk_tagged_batch', return_value=[{'status': 'chunked_needs_review'}]) as run:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(main.main(), 0)
                run.assert_called_once()
                if mode == 'cli':
                    self.assertFalse(run.call_args.args[1].export_enabled)


if __name__ == '__main__':
    unittest.main()
