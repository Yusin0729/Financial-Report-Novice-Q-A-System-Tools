"""檔名前綴、來源metadata與既有產物更名的合成測試。"""
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from schemas import NotesScope
from functions.markdown_processing.file_identity import filename_identity,markdown_filename
from functions.markdown_processing.load_source import load_source
from functions.experiments.export_output import migrate_markdown_filenames
from main import run_tag_markdown


class FilenameTests(unittest.TestCase):
    def test_year_stock_and_leading_zero_without_quarter_inference(self):
        self.assertEqual(filename_identity('2025_0012_processed.md'),('2025','0012'))
        self.assertIsNone(filename_identity('document.md'))
        self.assertEqual(markdown_filename(Path('2025Q4_2330_Financial_Report'),'raw'),'2025_2330_raw.md')

    def test_directory_loading_new_names_and_ambiguous_failure(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            p=Path(folder);(p/'2025_2330_processed.md').write_bytes(b'content')
            self.assertEqual(load_source(p)[0].name,'2025_2330_processed.md')
            (p/'2024_2330_processed.md').write_bytes(b'other')
            with self.assertRaises(ValueError):load_source(p)

    def test_metadata_reads_filename_only_and_keeps_unknown_period(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            p=Path(folder)/'2025_0012_processed.md'
            p.write_bytes('## 合併財務報告附註\n## 一、公司\n113及112年度比較\n'.encode('utf-8'))
            r=run_tag_markdown(p,replace(SETTINGS,export_enabled=False),notes_scope=NotesScope(2,3,hashlib.sha256(p.read_bytes()).hexdigest(),'synthetic_fixture'))
            self.assertEqual(r['metadata']['report_year'],'2025')
            self.assertEqual(r['metadata']['stock_code'],'0012')
            self.assertEqual(r['metadata']['report_period'],'')
            self.assertEqual(r['metadata']['company_name'],'')
            self.assertEqual(r['metadata_sources']['report_year'],'filename_prefix')

    def setup_files(self,p):
        settings=replace(SETTINGS,project_root=p)
        files=[]
        for root in [settings.markdown_output_dir,settings.markdown_processed_output_dir,settings.markdown_tagged_output_dir]:
            folder=root/'2025Q4_2330_Financial_Report'/'run';folder.mkdir(parents=True)
            source=folder/'document.md';source.write_bytes(b'original\r\n')
            (folder/'manifest.json').write_text(json.dumps({'source':{'path':str(files[0]) if files else 'file.pdf'}}),encoding='utf-8')
            files.append(source)
        return settings,files

    def test_migration_preserves_bytes_references_old_names_and_idempotence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            settings,files=self.setup_files(Path(folder))
            plan=migrate_markdown_filenames(settings)
            self.assertEqual(len(plan),3)
            self.assertTrue(all(p.exists() for p in files))
            migrate_markdown_filenames(settings,apply=True)
            for item in plan:self.assertEqual(Path(item['new']).read_bytes(),b'original\r\n')
            self.assertTrue(Path(plan[0]['new']).name.endswith('_document.md'))
            self.assertTrue(Path(plan[1]['new']).name.endswith('_processed.md'))
            self.assertTrue(Path(plan[2]['new']).name.endswith('_tagged.md'))
            m=json.loads((files[1].parent/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(m['source']['path'],plan[0]['new'])
            self.assertEqual(m['filename_migration']['renamed_files'][0]['old_name'],'document.md')
            self.assertEqual(migrate_markdown_filenames(settings,apply=True),[])

    def test_collision_fails_before_any_rename_and_synthetic_file_is_not_guessed(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            settings,files=self.setup_files(Path(folder))
            target=files[2].with_name('2025_2330_tagged.md');target.write_bytes(b'valid existing')
            with self.assertRaises(FileExistsError):migrate_markdown_filenames(settings,apply=True)
            self.assertTrue(all(p.exists() for p in files))
            self.assertEqual(target.read_bytes(),b'valid existing')
            synthetic=settings.markdown_output_dir/'synthetic';synthetic.mkdir()
            (synthetic/'page_1.md').write_bytes(b'synthetic')
            target.unlink()
            migrate_markdown_filenames(settings,apply=True)
            self.assertTrue((synthetic/'page_1.md').exists())


if __name__=='__main__':unittest.main()
