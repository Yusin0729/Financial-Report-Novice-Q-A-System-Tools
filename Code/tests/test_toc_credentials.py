"""只以暫存假金鑰驗證.env讀取；不讀專案真實金鑰、不連網。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.toc import TocSettings
from functions.integrations.gemini_toc import require_api_key


class TocCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '.env'
        self.config = TocSettings()
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_read_utf8_bom_quotes_comments_without_exporting_environment(self):
        self.path.write_text('# 本機設定\nGEMINI_API_KEY="FAKE_FILE_KEY" # 註解\nOTHER=unrelated\n',encoding='utf-8-sig')
        self.assertEqual(require_api_key(self.config,env_path=self.path),'FAKE_FILE_KEY')
        self.assertNotIn('GEMINI_API_KEY',os.environ)
        self.assertNotIn('OTHER',os.environ)

    def test_existing_environment_takes_priority_without_reading_file(self):
        os.environ['GEMINI_API_KEY']='FAKE_ENV_KEY'
        with patch('pathlib.Path.is_file',side_effect=AssertionError('不應讀檔')):
            self.assertEqual(require_api_key(self.config,env_path=self.path),'FAKE_ENV_KEY')

    def test_empty_environment_uses_file_and_rereads_updated_file(self):
        os.environ['GEMINI_API_KEY']=' '
        self.path.write_text('GEMINI_API_KEY=FAKE_FIRST\n',encoding='utf-8')
        self.assertEqual(require_api_key(self.config,env_path=self.path),'FAKE_FIRST')
        self.path.write_text('GEMINI_API_KEY=FAKE_SECOND\n',encoding='utf-8')
        self.assertEqual(require_api_key(self.config,env_path=self.path),'FAKE_SECOND')

    def test_missing_blank_or_wrong_variable_errors_do_not_include_contents(self):
        with self.assertRaisesRegex(ValueError,'尚未設定'):
            require_api_key(self.config,env_path=self.path)
        for content in ['GEMINI_API_KEY=\n','OTHER=FAKE_UNRELATED_SECRET\n']:
            self.path.write_text(content,encoding='utf-8')
            with self.assertRaises(ValueError) as error:
                require_api_key(self.config,env_path=self.path)
            self.assertNotIn('FAKE_UNRELATED_SECRET',str(error.exception))

    def test_does_not_expand_other_environment_variables(self):
        os.environ['UNRELATED_SECRET']='DO_NOT_READ'
        self.path.write_text('GEMINI_API_KEY=${UNRELATED_SECRET}\n',encoding='utf-8')
        self.assertEqual(require_api_key(self.config,env_path=self.path),'${UNRELATED_SECRET}')

    def test_invalid_encoding_error_does_not_reveal_file_bytes(self):
        self.path.write_bytes(b'GEMINI_API_KEY=FAKE_SECRET\xff')
        with self.assertRaisesRegex(ValueError,'UTF-8') as error:
            require_api_key(self.config,env_path=self.path)
        self.assertNotIn('FAKE_SECRET',str(error.exception))

    def test_only_explicit_project_file_is_loaded_not_current_directory(self):
        self.path.write_text('GEMINI_API_KEY=FAKE_OTHER_ROOT\n',encoding='utf-8')
        missing = self.path.parent / 'another_project' / '.env'
        with self.assertRaisesRegex(ValueError,'尚未設定'):
            require_api_key(self.config,env_path=missing)


if __name__=='__main__': unittest.main()
