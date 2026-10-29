"""只操作暫存.env與合成金鑰；不讀取真實金鑰、不呼叫API。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from Code.functions.embedding.api_settings import manage, public_settings, resolve_profile, config_path


class ApiSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='API 設定 測試 ')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{},clear=True);self.env.start();self.addCleanup(self.env.stop)
    def add(self,**overrides):
        request={'action':'add','name':'測試設定','purpose':'embedding','provider':'voyage',
                 'model':'voyage-finance-2','api_key':'FAKE-TEST-KEY-12345'}
        request.update(overrides)
        return manage(self.root,request)

    def test_key_only_env_and_never_returned(self):
        data=self.add()
        self.assertNotIn('FAKE-TEST-KEY',json.dumps(data))
        self.assertNotIn('FAKE-TEST-KEY',config_path(self.root).read_text(encoding='utf-8'))
        self.assertIn('FAKE-TEST-KEY',(self.root/'.env').read_text())
        profile,key=resolve_profile(self.root,data['profiles'][0]['id'],'embedding')
        self.assertEqual(key,'FAKE-TEST-KEY-12345')
        self.assertEqual(profile['model'],'voyage-finance-2')

    def test_shared_key_delete_removes_profiles_and_only_its_env_line(self):
        other='\ufeff# 保留中文\r\nUNRELATED=do-not-change\r\n'.encode('utf-8')
        (self.root/'.env').write_bytes(other)
        first=self.add()
        cid=first['credentials'][0]['id']
        data=self.add(purpose='rerank',model='rerank-3-lite',credential_id=cid,api_key=None)
        self.assertEqual(len(data['profiles']),2)
        self.assertEqual(len(data['credentials']),1)
        result=manage(self.root,{'action':'delete-key','id':cid})
        self.assertEqual(result['profiles'],[])
        self.assertEqual(result['credentials'],[])
        self.assertEqual((self.root/'.env').read_bytes(),other)
        with self.assertRaises(ValueError): resolve_profile(self.root,first['profiles'][0]['id'],'embedding')

    def test_delete_profile_keeps_shared_secret_until_explicit_key_delete(self):
        data=self.add();cid=data['credentials'][0]['id'];pid=data['profiles'][0]['id']
        result=manage(self.root,{'action':'delete-profile','id':pid})
        self.assertFalse(result['profiles']);self.assertEqual(result['credentials'][0]['id'],cid)
        self.assertIn('FAKE-TEST-KEY',(self.root/'.env').read_text())

    def test_legacy_voyage_shared_and_gpt_model_explicit(self):
        (self.root/'.env').write_text('VOYAGE_API_KEY=FAKE-LEGACY-KEY\nOPENAI_API_KEY=FAKE-OPENAI-KEY\n',encoding='utf-8')
        data=public_settings(self.root)
        self.assertEqual(len(data['profiles']),2)
        data=self.add(purpose='answer',provider='openai',model='gpt-test-only',credential_id='legacy_openai',api_key=None)
        p=next(p for p in data['profiles'] if p['provider']=='openai')
        self.assertEqual(resolve_profile(self.root,p['id'],'answer')[1],'FAKE-OPENAI-KEY')
        data=manage(self.root,{'action':'delete-key','id':'legacy_voyage'})
        self.assertFalse(any(p['provider']=='voyage' for p in data['profiles']))
        self.assertTrue(any(p['provider']=='openai' for p in data['profiles']))

    def test_environment_key_cannot_falsely_report_deleted(self):
        with patch.dict(os.environ,{'VOYAGE_API_KEY':'FAKE-EXTERNAL-KEY'}):
            data=public_settings(self.root)
            self.assertFalse(data['credentials'][0]['deletable'])
            with self.assertRaisesRegex(ValueError,'外部環境'): manage(self.root,{'action':'delete-key','id':'legacy_voyage'})
            self.assertTrue(public_settings(self.root)['profiles'])

    def test_reject_wrong_provider_models_and_invalid_keys(self):
        for overrides in ({'provider':'openai'},{'model':'other-embedding'},
                          {'purpose':'answer','provider':'openai','model':'gemini-wrong'},
                          {'api_key':'FAKE\nINJECTED=KEY'},{'api_key':None}):
            with self.assertRaises(ValueError): self.add(**overrides)
        self.assertFalse((self.root/'.env').exists())

    def test_malformed_config_never_exposes_unknown_secret_fields(self):
        path=config_path(self.root);path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'version':1,'credentials':[{'api_key':'FAKE-SECRET'}],'profiles':[]}),encoding='utf-8')
        with self.assertRaises(ValueError) as error: public_settings(self.root)
        self.assertNotIn('FAKE-SECRET',str(error.exception))

    def test_failed_profile_save_rolls_back_new_env_key(self):
        with patch('Code.functions.embedding.api_settings.save_config',side_effect=OSError('fake')):
            with self.assertRaises(RuntimeError): self.add()
        self.assertNotIn('FAKE-TEST-KEY',(self.root/'.env').read_text())


if __name__=='__main__':unittest.main()
