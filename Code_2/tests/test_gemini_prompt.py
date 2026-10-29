import unittest,json,tempfile
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from Code_2.config.qa import QASettings,SYSTEM_PROMPT,gemini_prompt
from Code_2.functions.qa.services import GeminiAnswerer
from Code_2.config.embedding import Settings
from Code_2.functions.web.service import validate_task,execute_task

class GeminiPromptTests(unittest.TestCase):
    def test_custom_prompt_is_sent_to_count_and_generate(self):
        for custom in (None,'請使用繁體中文，清楚列出公式與單位。'):
            with self.subTest(custom=custom):
                adapter=GeminiAnswerer('unused',replace(QASettings(),gemini_system_prompt=custom))
                calls=[]
                def post(method,body):
                    calls.append((method,body))
                    if method=='countTokens':return {'totalTokens':100}
                    return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'平均值 = (100 + 200) / 2 = 150 百萬元。[S1]'}]}}]}
                adapter.post=post
                _,usage=adapter.answer('問題',[{'id':'S1','doc_id':'doc','page':[1],'text':'正文'}])
                counted=calls[0][1]['generateContentRequest'];generated=calls[1][1]
                for body in (counted,generated):
                    self.assertEqual(body['systemInstruction']['parts'][0]['text'],custom or SYSTEM_PROMPT)
                    self.assertNotIn('responseSchema',body['generationConfig'])
                self.assertEqual(usage['prompt_source'],'custom' if custom else 'default')

    def test_invalid_prompt_rejected_before_network(self):
        for value in ('','  ',42,'x'*20001):
            with self.subTest(value=type(value).__name__),self.assertRaises(ValueError):gemini_prompt(value)

    def test_web_request_survives_validation_and_reaches_qa(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=Settings(project_root=Path(directory))
            request={'action':'query','question':'營收？','backend':'bge','collection':'financial_'+'a'*24,
                     'mode':'answer','retrieve_k':50,'evidence_k':10,'rerank_enabled':False,
                     'gemini_system_prompt':'自訂指令'}
            clean=validate_task(request,settings)
            with patch('Code_2.functions.qa.run.run_question',return_value={'status':'answered'}) as run:
                execute_task(clean,settings)
            self.assertEqual(run.call_args.kwargs['qa'].gemini_system_prompt,'自訂指令')
            for value in ('',3,'x'*20001):
                with self.assertRaises(ValueError):validate_task({**request,'gemini_system_prompt':value},settings)

if __name__=='__main__':unittest.main()
