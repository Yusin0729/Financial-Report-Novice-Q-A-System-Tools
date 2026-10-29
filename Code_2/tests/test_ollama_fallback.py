import json
import unittest
import urllib.error
from unittest.mock import Mock, MagicMock, patch
from dataclasses import replace
from Code_2.config.qa import QASettings
from Code_2.functions.qa.services import GeminiAnswerer
from Code_2.functions.qa.ollama_answer import OllamaAnswerer

E=[{'id':'S1','doc_id':'doc','page':[1],'text':'營收100'}]
ANSWER={'status':'answered','format':'markdown','text':'答案100 [S1]','calculation_source':'llm'}

class FallbackTests(unittest.TestCase):
    def test_primary_success_does_not_call_local(self):
        a=GeminiAnswerer('unused',QASettings());a._answer=Mock(return_value=(ANSWER,{'model':'gemini-test'}))
        with patch.object(OllamaAnswerer,'answer') as local:
            _,u=a.answer('問題',E)
        local.assert_not_called();self.assertFalse(u['fallback_used']);self.assertEqual(u['provider'],'gemini')

    def test_primary_failure_passes_exact_question_evidence_prompt(self):
        a=GeminiAnswerer('unused',QASettings(gemini_system_prompt='用繁體中文'))
        a.post=Mock(side_effect=[{'totalTokens':10},RuntimeError('Gemini HTTP 503')])
        def local(instance,question,evidence):
            self.assertEqual(question,'原題');self.assertIs(evidence,E)
            self.assertEqual(instance.settings.gemini_system_prompt,'用繁體中文')
            return ANSWER,{'provider':'ollama','model':'llama3.1:8b','input_tokens':20}
        with patch.object(OllamaAnswerer,'answer',autospec=True,side_effect=local) as call:
            _,u=a.answer('原題',E)
        self.assertEqual(call.call_count,1);self.assertTrue(u['fallback_used'])
        self.assertEqual(u['primary_attempt']['input_tokens'],10)
        self.assertIn('503',u['primary_attempt']['error'])

    def test_both_fail_preserves_both_causes(self):
        a=GeminiAnswerer('unused',QASettings());a.post=Mock(side_effect=RuntimeError('Gemini HTTP 429'))
        with patch.object(OllamaAnswerer,'answer',side_effect=RuntimeError('Ollama無法連線')):
            with self.assertRaisesRegex(RuntimeError,'429.*Ollama'):a.answer('題',E)
        self.assertTrue(a.last_attempt['fallback_used']);self.assertIn('fallback_error',a.last_attempt)

    def test_invalid_user_prompt_never_falls_back(self):
        a=GeminiAnswerer('unused',QASettings(gemini_system_prompt=''))
        with patch.object(OllamaAnswerer,'answer') as call,self.assertRaises(ValueError):a.answer('題',E)
        call.assert_not_called()

    def local(self,response,qa=None):
        opener=MagicMock();opener.open.return_value.__enter__.return_value.read.return_value=json.dumps(response).encode()
        return OllamaAnswerer(qa or QASettings(),opener),opener

    def test_local_request_and_usage(self):
        a,o=self.local({'done':True,'done_reason':'stop','model':'llama3.1:8b','message':{'content':'答案 [S1]'},'prompt_eval_count':20,'eval_count':3})
        ans,u=a.answer('題',E);req=o.open.call_args.args[0];body=json.loads(req.data)
        self.assertEqual(req.full_url,'http://127.0.0.1:11434/api/chat')
        self.assertFalse(body['stream']);self.assertEqual(body['options']['num_ctx'],32768)
        self.assertEqual(json.loads(body['messages'][1]['content'])['evidence'],E)
        self.assertEqual(ans['text'],'答案 [S1]');self.assertTrue(u['local_inference'])
        self.assertNotIn('x-goog-api-key',dict(req.header_items()))

    def test_empty_truncated_or_incomplete_rejected(self):
        for data in ({'done':True,'done_reason':'length','message':{'content':'partial'}},
                     {'done':False,'message':{'content':'partial'}},
                     {'done':True,'done_reason':'stop','message':{'content':''}}):
            a,_=self.local(data)
            with self.assertRaises(ValueError):a.answer('題',E)

    def test_oversized_input_not_sent(self):
        a,o=self.local({},replace(QASettings(),ollama_context_tokens=4200))
        with self.assertRaisesRegex(ValueError,'未截斷'):a.answer('題',E)
        o.open.assert_not_called()

    def test_http_error_does_not_leak_body(self):
        a,o=self.local({});o.open.side_effect=urllib.error.HTTPError('url',404,'SECRET',{},None)
        with self.assertRaisesRegex(RuntimeError,'404') as error:a.answer('題',E)
        self.assertNotIn('SECRET',str(error.exception))

if __name__=='__main__':unittest.main()
