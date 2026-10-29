"""前處理資料契約、表格保真與批次失敗行為；不使用真實API或模型。"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from Code_2.config.embedding import Settings
from Code_2.functions.embedding.batch import prepare_batch
from Code_2.functions.embedding.prepare import prepare_document
from Code_2.functions.embedding.table_text import convert_content


def fixture(content=None, kind='text'):
    doc_id = '2025Q4_2330_Financial_Report'
    content = content or '<!-- Page: 2330_2025_P41 -->\n財報金額(1,234.50)，-6.2%。'
    return {'schema_version': 'financial-chunks/1.0', 'rule_version': 'heading-content-chunks/1.0',
            'doc_id': doc_id, 'source_sha256': 'a' * 64, 'excluded_prefix_end': 0,
            'chunks': [{'chunk_id': doc_id + '__c00001', 'doc_id': doc_id, 'years': [2025],
                        'page': [41], 'title': {'main_title': '合併財務報表附錄',
                                              'heading': {'level': 2, 'text': '十七、應付公司債', 'children': []}},
                        'data_tags': [], 'content_type': kind, 'content': content,
                        'body_char_count': 10, 'source_spans': [{'start': 0, 'end': len(content), 'pages': [41]}],
                        'cut_reason': 'complete_table' if kind == 'table' else 'eof'}]}


def prepared(doc):
    return prepare_document(doc, input_sha256='b' * 64)


class TableTests(unittest.TestCase):
    def test_spans_repeat_only_merged_cells(self):
        text, grids = convert_content('<table><tr><th rowspan="2">債券</th><th colspan="2">金額</th></tr>'
                                      '<tr><td>2024</td><td>2025</td></tr><tr><td>甲</td><td></td><td>(1,234.50)</td></tr></table>')
        self.assertEqual(grids[0], [['債券', '金額', '金額'], ['債券', '2024', '2025'], ['甲', '', '(1,234.50)']])
        self.assertIn('| 甲 |  | (1,234.50) |', text)

    def test_cross_page_preserves_intermediate_text(self):
        table = '<table><tr><td>1,234.50</td></tr></table>'
        text, tables = convert_content(table + '接 次 頁<page_end><!-- Page: 2330_2025_P42 -->'
                                       '<page_start>承 前 頁' + table)
        self.assertEqual(len(tables), 2)
        self.assertEqual(text.count('1,234.50'), 2)
        self.assertIn('接 次 頁', text)
        self.assertIn('承 前 頁', text)
        self.assertNotIn('Page:', text)

    def test_symbols_entities_and_line_breaks(self):
        text, grid = convert_content('<table><tr><td>A|B<br>C &amp; D</td><td>$(1,234.50) -6.2% 仟元</td></tr></table>')
        self.assertIn(r'A\|B<br>C & D', text)
        self.assertEqual(grid[0][0][0], 'A|B\nC & D')
        self.assertIn('$(1,234.50) -6.2% 仟元', text)

    def test_bad_tables_rejected(self):
        bad = ['<table><tr><td>未閉合', '<table></table>', '<table><table></table></table>',
               '<table><tr><td rowspan="0">a</td></tr></table>',
               '<table><tr><td rowspan="2">a</td></tr></table>',
               '<table>表外異常文字<tr><td>a</td></tr></table>',
               '<table><tr><td>a</th></tr></table>',
               '<table><tr><td>a</td><td rowspan="2">b</td></tr><tr><td colspan="2">c</td></tr></table>']
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                convert_content(raw)

    def test_control_tags_removed_but_heading_text_kept(self):
        text, _ = convert_content('<!-- Page: 2330_2025_P41 --><content_start><hd3>(一) 基礎</hd3>'
                                  '原文</content_end><page_end>')
        self.assertIn('(一) 基礎', text)
        self.assertIn('原文', text)
        self.assertNotIn('<hd3>', text)
        self.assertNotIn('content_start', text)

    def test_unknown_tags_rejected(self):
        with self.assertRaises(ValueError):
            convert_content('<script>不能默默刪掉</script>')


class DocumentTests(unittest.TestCase):
    def test_v3_heading_can_be_unknown_without_fabricating_hd2(self):
        doc = fixture('查核報告正文。')
        doc['schema_version'] = 'financial-chunks/3.0'
        doc['chunks'][0]['title'] = {'main_title': '會計師查核報告', 'heading': None}
        result = prepared(doc)['chunks'][0]
        self.assertEqual(result['metadata']['main_title'], '會計師查核報告')
        self.assertEqual(result['metadata']['hd2_title'], '')
        self.assertIn('查核報告正文。', result['embedding_text'])
        doc['schema_version'] = 'financial-chunks/2.0'
        with self.assertRaises(ValueError):
            prepared(doc)

    def test_source_unchanged_and_metadata_typed(self):
        doc = fixture()
        before = deepcopy(doc)
        result = prepared(doc)
        self.assertEqual(doc, before)
        c = result['chunks'][0]
        self.assertEqual(c['original_chunk'], before['chunks'][0])
        self.assertEqual(c['metadata']['stock_code'], '2330')
        self.assertNotIn('report_year', c['metadata'])
        self.assertEqual(c['metadata']['years'], [2025])
        self.assertEqual(c['metadata']['page'], [41])
        self.assertEqual(c['metadata']['data_tags'], [])
        self.assertIsNone(c['preparation']['token_count'])
        self.assertEqual(result['token_check_status'], 'pending_model_selection')
        c['original_chunk']['page'].append(99)
        self.assertEqual(doc, before)

    def test_heading_tree_preserved_as_outline(self):
        doc = fixture()
        doc['chunks'][0]['title']['heading']['children'] = [
            {'level': 3, 'text': '(一)甲', 'children': []},
            {'level': 3, 'text': '(二)乙', 'children': [{'level': 4, 'text': '1.丙', 'children': []}]}]
        c = prepared(doc)['chunks'][0]
        self.assertIn('本塊小節索引：\n(一)甲\n(二)乙 > 1.丙', c['embedding_text'])
        self.assertEqual(c['original_chunk']['title'], doc['chunks'][0]['title'])

    def test_invalid_document_contract(self):
        mutations = [lambda d: d.update(schema_version='financial-toc/2.0'),
                     lambda d: d['chunks'].append(deepcopy(d['chunks'][0])),
                     lambda d: d['chunks'][0].update(years=['2025']),
                     lambda d: d['chunks'][0].update(page=[True]),
                     lambda d: d['chunks'][0].update(content='  '),
                     lambda d: d['chunks'][0]['title']['heading'].update(level=3),
                     lambda d: d['chunks'][0].update(content='<!-- Page: 2303_2025_P41 -->錯公司'),
                     lambda d: d['chunks'][0].update(content='<!-- Page: 2330_2025_P42 -->錯頁'),
                     lambda d: d['chunks'][0].update(content_type='table')]
        for mutate in mutations:
            doc = fixture()
            mutate(doc)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                prepared(doc)

    def test_blank_boundary_page_not_added_to_metadata(self):
        doc = fixture('<!-- Page: 2330_2025_P40 -->\n\n<!-- Page: 2330_2025_P41 -->\n有效正文')
        doc['chunks'][0]['source_spans'].insert(0, {'start': 0, 'end': 1, 'pages': [40]})
        result = prepared(doc)
        self.assertEqual(result['chunks'][0]['metadata']['page'], [41])

    def test_no_truncation_even_large_table(self):
        raw = '<table>' + ''.join(f'<tr><td>{i}</td><td>金額 (9,876.50)</td></tr>' for i in range(500)) + '</table>'
        result = prepared(fixture(raw, 'table'))['chunks'][0]
        self.assertIn('| 499 | 金額 (9,876.50) |', result['embedding_text'])
        self.assertEqual(result['original_chunk']['content'], raw)
        self.assertIsNone(result['preparation']['token_count'])


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='財報 前處理 ')
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(project_root=Path(self.tmp.name))
        self.batch = self.settings.input_dir / 'Financial_20261022_01-23-16'
        (self.batch / 'Record').mkdir(parents=True)
        self.source, self.origin = self.add_source()

    def add_source(self, stock='2330', valid=True):
        doc = fixture()
        if stock != '2330':
            doc = json.loads(json.dumps(doc, ensure_ascii=False).replace('2330', stock))
        raw = json.dumps(doc, ensure_ascii=False).encode('utf-8')
        source = self.batch / f'2025_{stock}_chunk.json'
        source.write_bytes(raw)
        origin = {'schema_version': 'chunk-run/1.0', 'batch': self.batch.name, 'status': 'chunked_needs_review',
                  'doc_id': doc['doc_id'], 'source_sha256': doc['source_sha256'], 'chunk_count': 1,
                  'outputs': {'json': {'filename': source.name, 'sha256': hashlib.sha256(raw).hexdigest() if valid else 'bad'}}}
        record = self.batch / 'Record' / f'2025_{stock}_reocrd'
        record.write_text(json.dumps(origin), encoding='utf-8')
        return source, record

    def test_no_export_and_source_bytes_unchanged(self):
        before = self.source.read_bytes()
        result = prepare_batch(self.batch, replace(self.settings, export_enabled=False))[0]
        self.assertEqual(result['status'], 'prepared_needs_review')
        self.assertFalse(self.settings.output_dir.exists())
        self.assertEqual(self.source.read_bytes(), before)

    def test_export_pair_hashes_and_collision(self):
        row = prepare_batch(self.batch, self.settings)[0]
        target = Path(row['output_dir'])
        record = json.loads((target / 'Record/2025_2330_reocrd').read_text(encoding='utf-8'))
        for info in record['outputs'].values():
            self.assertEqual(hashlib.sha256((target / info['filename']).read_bytes()).hexdigest(), info['sha256'])
        with self.assertRaises(FileExistsError):
            prepare_batch(self.batch, self.settings)

    def test_record_hash_mismatch_is_reported_and_other_document_continues(self):
        self.add_source('2303', valid=False)
        rows = prepare_batch(self.batch, self.settings)
        self.assertEqual([r['status'] for r in rows], ['prepared_needs_review', 'prepared_needs_review'])
        self.assertIn('雜湊', rows[0]['source_record_issue'])
        target = self.settings.output_dir / self.batch.name
        self.assertTrue((target / '2025_2303_prepared.json').exists())
        self.assertTrue((target / 'Record/2025_2303_reocrd').exists())

    def test_all_collisions_checked_before_processing(self):
        self.add_source('2303')
        target = self.settings.output_dir / self.batch.name
        target.mkdir(parents=True)
        (target / '2025_2330_prepared.md').write_text('既有成果', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            prepare_batch(self.batch, self.settings)
        self.assertFalse((target / '2025_2303_prepared.json').exists())

    def test_partial_write_cleanup_and_failed_record(self):
        actual_open = Path.open
        def fail_md(path, *args, **kwargs):
            if path.name.endswith('_prepared.md'):
                raise OSError('模擬磁碟錯誤')
            return actual_open(path, *args, **kwargs)
        with patch.object(Path, 'open', fail_md):
            row = prepare_batch(self.batch, self.settings)[0]
        self.assertEqual(row['status'], 'failed')
        target = self.settings.output_dir / self.batch.name
        self.assertFalse((target / '2025_2330_prepared.json').exists())
        self.assertFalse((target / '2025_2330_prepared.md').exists())
        record = json.loads((target / 'Record/2025_2330_reocrd').read_text(encoding='utf-8'))
        self.assertNotIn('outputs', record)

    def test_interrupt_stops_batch(self):
        self.add_source('2303')
        with patch('Code_2.functions.embedding.batch.prepare_document', side_effect=KeyboardInterrupt):
            rows = prepare_batch(self.batch, self.settings)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'interrupted')

    def test_missing_record_is_reported_but_preparation_uses_chunk_json(self):
        self.origin.unlink()
        row = prepare_batch(self.batch, self.settings)[0]
        self.assertEqual(row['status'], 'prepared_needs_review')
        self.assertIn('不存在', row['source_record_issue'])

    def test_prepared_json_can_load_without_output_record(self):
        from Code_2.functions.embedding.load_prepared import load_prepared
        prepare_batch(self.batch, self.settings)
        output = self.settings.output_dir / self.batch.name
        (output / 'Record' / '2025_2330_reocrd').unlink()
        doc, digest, report = load_prepared(output / '2025_2330_prepared.json')
        self.assertEqual(doc['doc_id'], fixture()['doc_id'])
        self.assertEqual(len(digest), 64)
        self.assertIn('不存在', report['source_record_issue'])

    def test_outside_batch_rejected(self):
        with self.assertRaises(ValueError):
            prepare_batch(self.settings.project_root, self.settings)


class EntrypointTests(unittest.TestCase):
    def test_build_cli_moved_to_code(self):
        from Code_2.main import main
        with self.assertRaises(SystemExit) as error:
            main(['--prepare-batch', 'some-batch'])
        self.assertEqual(error.exception.code, 2)

    def test_main_from_other_working_directory(self):
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'Code_2/main.py'), '--help'],
                              cwd=root / 'Code_2', capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('--no-export', proc.stdout)

    def test_menu_exit(self):
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'Code_2/main.py')],
                              input='0\n', capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == '__main__':
    unittest.main()
