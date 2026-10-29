import json
import tempfile
import unittest
from pathlib import Path
from Code_2.config.embedding import Settings
from Code_2.functions.web import files

class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings=Settings(project_root=Path(self.temp.name));self.root=self.settings.project_root
        (self.root/'Output'/'batch').mkdir(parents=True)
        (self.root/'Output'/'batch'/'答案.md').write_text('正文',encoding='utf-8')
        (self.root/'Output'/'.env').write_text('SECRET',encoding='utf-8')

    def test_listing_preview_and_hidden_exclusion(self):
        self.assertEqual([e['name'] for e in files.listing(self.settings,'output')['entries']],['batch'])
        self.assertEqual(files.preview(self.settings,'output','batch/答案.md')['text'],'正文')
        self.assertEqual(files.listing(self.settings,'sources')['total'],0)

    def test_oversized_preview_is_bounded(self):
        (self.root/'Output'/'big.json').write_text('a'*(files.PREVIEW_BYTES+20))
        r=files.preview(self.settings,'output','big.json');self.assertTrue(r['truncated']);self.assertEqual(len(r['text']),files.PREVIEW_BYTES)

    def test_path_escape_and_secret_paths_rejected(self):
        for area,path in [('output','../AGENTS.md'),('output','batch/../../.env'),('output','.env'),('output','D:/secret'),('output','/batch'),('bad','')]:
            with self.subTest(path=path),self.assertRaises(ValueError):files.resolve(self.settings,area,path)

    def test_confirm_then_trash_and_restore(self):
        snap=files.folder_snapshot(self.settings,'output','batch');self.assertEqual(snap['files'],1)
        with self.assertRaises(ValueError):files.trash(self.settings,{**snap,'confirm_name':'wrong'})
        self.assertTrue((self.root/'Output'/'batch').exists())
        files.trash(self.settings,{**snap,'confirm_name':'batch'})
        self.assertFalse((self.root/'Output'/'batch').exists())
        row=files.trash_list(self.settings)['entries'][0];files.restore(self.settings,row['id'])
        self.assertTrue((self.root/'Output'/'batch'/'答案.md').exists())
        self.assertEqual(files.trash_list(self.settings)['entries'],[])

    def test_changed_folder_requires_new_confirmation(self):
        snap=files.folder_snapshot(self.settings,'output','batch')
        (self.root/'Output'/'batch'/'new.txt').write_text('new')
        with self.assertRaises(ValueError):files.trash(self.settings,{**snap,'confirm_name':'batch'})

    def test_root_cannot_be_removed_and_restore_cannot_overwrite(self):
        with self.assertRaises(ValueError):files.folder_snapshot(self.settings,'output','')
        snap=files.folder_snapshot(self.settings,'output','batch');files.trash(self.settings,{**snap,'confirm_name':'batch'})
        (self.root/'Output'/'batch').mkdir();row=files.trash_list(self.settings)['entries'][0]
        with self.assertRaises(ValueError):files.restore(self.settings,row['id'])

if __name__=='__main__':unittest.main()
