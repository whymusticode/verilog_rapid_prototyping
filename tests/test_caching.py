from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from py2v.client import Client


class _FakeUsage:
    def __init__(
        self,
        input_tokens: int = 10,
        output_tokens: int = 3,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _FakeBlock:
    def __init__(self, *, btype: str, text: str = "", bid: str = "", name: str = "", binput=None):
        self.type = btype
        self.text = text
        self.id = bid
        self.name = name
        self.input = binput or {}


class _FakeResponse:
    def __init__(self, content):
        self.stop_reason = "end_turn"
        self.content = content
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, make_response):
        self._make_response = make_response
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self._make_response(kwargs)


class _FakeAnthropicClient:
    def __init__(self, make_response):
        self.messages = _FakeMessages(make_response)


class CacheTests(unittest.TestCase):
    def test_request_key_stable_for_dict_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"ANTHROPIC_API_KEY": "dummy", "PY2V_CACHE_DIR": tmp}
            with patch.dict("os.environ", env, clear=False):
                with patch(
                    "py2v.client.anthropic.Anthropic",
                    lambda: _FakeAnthropicClient(
                        lambda _: _FakeResponse([_FakeBlock(btype="text", text="ok")])
                    ),
                ):
                    c = Client(monitor_log=None)
                    base = {
                        "model": c.model,
                        "max_tokens": c.max_tokens,
                        "messages": [{"role": "user", "content": [{"type": "text", "text": "x"}]}],
                        "tools": [{"name": "edit", "input_schema": {"a": 1, "b": 2}}],
                    }
                    same_semantics = {
                        "model": c.model,
                        "max_tokens": c.max_tokens,
                        "messages": [{"role": "user", "content": [{"text": "x", "type": "text"}]}],
                        "tools": [{"input_schema": {"b": 2, "a": 1}, "name": "edit"}],
                    }
                    self.assertEqual(c._request_cache_key(base), c._request_cache_key(same_semantics))

    def test_chat_cache_hit_skips_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            holder = {}

            def make_client():
                client = _FakeAnthropicClient(
                    lambda _: _FakeResponse([_FakeBlock(btype="text", text="first")])
                )
                holder["messages"] = client.messages
                return client

            env = {"ANTHROPIC_API_KEY": "dummy", "PY2V_CACHE_DIR": tmp}
            with patch.dict("os.environ", env, clear=False):
                with patch("py2v.client.anthropic.Anthropic", make_client):
                    c = Client(monitor_log=None, cache_enabled=True)
                    req = [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
                    r1 = c.chat(messages=req)
                    r2 = c.chat(messages=req)
                    self.assertEqual(holder["messages"].calls, 1)
                    self.assertEqual(r1.text, "first")
                    self.assertEqual(r2.text, "first")
                    self.assertEqual(c.cache_hits, 1)
                    self.assertEqual(c.cache_misses, 1)
                    self.assertEqual(c.usage.input_tokens, 10)

    def test_cache_bypass_forces_live_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            holder = {}

            def make_client():
                client = _FakeAnthropicClient(
                    lambda _: _FakeResponse([_FakeBlock(btype="text", text="live")])
                )
                holder["messages"] = client.messages
                return client

            env = {"ANTHROPIC_API_KEY": "dummy", "PY2V_CACHE_DIR": tmp}
            with patch.dict("os.environ", env, clear=False):
                with patch("py2v.client.anthropic.Anthropic", make_client):
                    c = Client(monitor_log=None, cache_enabled=True, cache_bypass=True)
                    req = [{"role": "user", "content": [{"type": "text", "text": "same"}]}]
                    c.chat(messages=req)
                    c.chat(messages=req)
                    self.assertEqual(holder["messages"].calls, 2)
                    self.assertEqual(c.cache_hits, 0)

    def test_cache_separates_model_and_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"ANTHROPIC_API_KEY": "dummy", "PY2V_CACHE_DIR": tmp}
            with patch.dict("os.environ", env, clear=False):
                with patch(
                    "py2v.client.anthropic.Anthropic",
                    lambda: _FakeAnthropicClient(
                        lambda _: _FakeResponse([_FakeBlock(btype="text", text="x")])
                    ),
                ):
                    c1 = Client(model="model-a", monitor_log=None)
                    c2 = Client(model="model-b", monitor_log=None)
                    req = [{"role": "user", "content": [{"type": "text", "text": "t"}]}]
                    k1 = c1._request_cache_key(
                        {
                            "model": c1.model,
                            "max_tokens": c1.max_tokens,
                            "messages": req,
                            "tools": [{"name": "one"}],
                        }
                    )
                    k2 = c2._request_cache_key(
                        {
                            "model": c2.model,
                            "max_tokens": c2.max_tokens,
                            "messages": req,
                            "tools": [{"name": "one"}],
                        }
                    )
                    k3 = c1._request_cache_key(
                        {
                            "model": c1.model,
                            "max_tokens": c1.max_tokens,
                            "messages": req,
                            "tools": [{"name": "two"}],
                        }
                    )
                    self.assertNotEqual(k1, k2)
                    self.assertNotEqual(k1, k3)


if __name__ == "__main__":
    unittest.main()
