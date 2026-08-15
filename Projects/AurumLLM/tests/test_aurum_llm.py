import unittest

from Projects.AurumLLM.aurum_llm import AurumLLM, AurumLLMConfig, AurumLLMError


class FakeAurumLLM(AurumLLM):
    def __init__(self, responses):
        super().__init__(AurumLLMConfig())
        self.responses = list(responses)
        self.calls = []

    def _request_json(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


class AurumLLMContractTests(unittest.TestCase):
    def test_health_uses_local_runtime_contract(self):
        client = FakeAurumLLM([{"status": "ok"}])
        result = client.health()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(client.calls[0][0:2], ("GET", "/health"))

    def test_chat_uses_stable_model_alias_and_tool_surface(self):
        client = FakeAurumLLM([
            {
                "choices": [
                    {
                        "message": {
                            "content": "ready",
                            "tool_calls": [{"id": "call-1", "type": "function"}],
                        }
                    }
                ]
            }
        ])
        reply = client.chat(
            [{"role": "user", "content": "status"}],
            tools=[{"type": "function", "function": {"name": "probe"}}],
        )
        method, path, payload = client.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(payload["model"], "aurum-seed")
        self.assertEqual(payload["tools"][0]["function"]["name"], "probe")
        self.assertEqual(reply.content, "ready")
        self.assertEqual(reply.tool_calls[0]["id"], "call-1")

    def test_reasoning_content_is_preserved_without_becoming_authority(self):
        client = FakeAurumLLM([
            {
                "choices": [
                    {"message": {"content": "", "reasoning_content": "candidate reasoning"}}
                ]
            }
        ])
        reply = client.chat([{"role": "user", "content": "analyze"}])
        self.assertEqual(reply.reasoning_content, "candidate reasoning")

    def test_missing_choices_fail_closed(self):
        client = FakeAurumLLM([{"choices": []}])
        with self.assertRaises(AurumLLMError):
            client.chat([{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    unittest.main()
