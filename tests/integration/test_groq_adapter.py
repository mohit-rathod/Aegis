import json
import unittest
import httpx
from support_assistant.adapters.groq.async_client import AsyncGroqClient
from support_assistant.domain.errors import ProviderError

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_payload_and_gpt_oss_reasoning(self):
        def respond(request):
            body=json.loads(request.content)
            self.assertEqual(body['response_format'],{'type':'json_object'})
            self.assertEqual(body['reasoning_effort'],'low')
            self.assertTrue(str(request.url).endswith('/openai/v1/chat/completions'))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"allowed":true,"reason":"ok"}'}}]})
        client=AsyncGroqClient('dummy-key','openai/gpt-oss-20b',transport=httpx.MockTransport(respond))
        try:self.assertTrue((await client.complete_json('Return JSON',{}))['allowed'])
        finally:await client.aclose()

    async def test_http_failure_does_not_expose_provider_body(self):
        client=AsyncGroqClient('dummy-key','openai/gpt-oss-20b',transport=httpx.MockTransport(lambda request:httpx.Response(401,json={'error':{'message':'private-provider-body'}})))
        try:
            with self.assertRaises(ProviderError) as captured:await client.complete_json('JSON',{})
            self.assertEqual(str(captured.exception),'groq_http_401')
        finally:await client.aclose()

    async def test_whisper_rejected_before_request(self):
        with self.assertRaises(ValueError):AsyncGroqClient('dummy','whisper-large-v3-turbo')
