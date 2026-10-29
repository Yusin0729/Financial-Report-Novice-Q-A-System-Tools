"""簡易三用途介面：僅暫存假金鑰，無外部請求。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from Code.functions.embedding.api_settings import manage, public_settings, resolve_profile, config_path


class SimpleApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{},clear=True);self.env.start();self.addCleanup(self.env.stop)
    def save(self,purpose='embedding',provider='voyage',model='voyage-finance-2',key='FAKE-SLOT-KEY-123'):
        return manage(self.root,{'action':'save-slot','purpose':purpose,'provider':provider,'model':model,'api_key':key})
    def test_three_slots_keep_one_profile_per_purpose_and_never_expose_keys(self):
        self.save();self.save('rerank',model='rerank-3-lite');data=self.save('answer','gemini','gemini-test')
        self.assertEqual(len(data['profiles']),3)
        self.assertTrue(all(data['slots'].values()))
        self.assertNotIn('FAKE-SLOT-KEY',json.dumps(data))
        self.assertNotIn('FAKE-SLOT-KEY',config_path(self.root).read_text())
    def test_replace_key_keeps_profile_id_and_removes_unused_secret(self):
        first=self.save();pid=first['slots']['embedding']['id']
        second=self.save(key='FAKE-REPLACEMENT-KEY-456')
        self.assertEqual(second['slots']['embedding']['id'],pid)
        self.assertEqual(len(second['profiles']),1)
        self.assertNotIn('FAKE-SLOT-KEY-123',(self.root/'.env').read_text())
        self.assertEqual(resolve_profile(self.root,pid,'embedding')[1],'FAKE-REPLACEMENT-KEY-456')
    def test_blank_key_keeps_secret_but_provider_switch_requires_new_key(self):
        self.save('answer','gemini','gemini-test')
        data=self.save('answer','gemini','gemini-updated',key='')
        self.assertEqual(data['slots']['answer']['model'],'gemini-updated')
        with self.assertRaises(ValueError):self.save('answer','openai','gpt-test',key='')
        data=self.save('answer','openai','gpt-test',key='FAKE-OPENAI-KEY')
        self.assertEqual(data['slots']['answer']['provider'],'openai')
        self.assertEqual(len(data['profiles']),1)
    def test_delete_legacy_embedding_preserves_shared_rerank_key(self):
        (self.root/'.env').write_text('VOYAGE_API_KEY=FAKE-SHARED-KEY\nUNRELATED=keep\n',encoding='utf-8')
        data=manage(self.root,{'action':'delete-slot','purpose':'embedding'})
        self.assertIsNone(data['slots']['embedding'])
        self.assertIsNotNone(data['slots']['rerank'])
        self.assertIn('FAKE-SHARED-KEY',(self.root/'.env').read_text())
        data=manage(self.root,{'action':'delete-slot','purpose':'rerank'})
        self.assertIsNone(data['slots']['rerank'])
        self.assertNotIn('FAKE-SHARED-KEY',(self.root/'.env').read_text())
        self.assertIn('UNRELATED=keep',(self.root/'.env').read_text())
    def test_legacy_existing_key_can_be_kept_without_copying_secret(self):
        (self.root/'.env').write_text('VOYAGE_API_KEY=FAKE-LEGACY-KEY\n',encoding='utf-8')
        data=self.save(key='')
        self.assertEqual(len([p for p in data['profiles'] if p['purpose']=='embedding']),1)
        pid=data['slots']['embedding']['id']
        self.assertEqual(resolve_profile(self.root,pid,'embedding')[1],'FAKE-LEGACY-KEY')
    def test_failed_save_rolls_back_env_and_external_key_is_not_falsely_deleted(self):
        self.save();before=(self.root/'.env').read_bytes();config=config_path(self.root).read_bytes()
        with patch('Code.functions.embedding.api_settings.save_config',side_effect=OSError('mock disk')):
            with self.assertRaises(OSError):self.save(key='FAKE-NEW-KEY')
        self.assertEqual((self.root/'.env').read_bytes(),before)
        self.assertEqual(config_path(self.root).read_bytes(),config)
        with patch.dict(os.environ,{'GEMINI_API_KEY':'FAKE-EXTERNAL-KEY'}):
            with self.assertRaisesRegex(ValueError,'外部環境'):manage(self.root,{'action':'delete-slot','purpose':'answer'})
    def test_wrong_provider_and_model_rejected(self):
        for args in [('embedding','openai','gpt-test'),('embedding','voyage','other'),('answer','openai','gemini-test')]:
            with self.assertRaises(ValueError):self.save(*args)
