"""
helper_llm.py 単体テスト

テスト実行:
    pytest tests/helpers/test_helper_llm.py -v
"""

import os
import sys
from types import SimpleNamespace
from typing import List
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel

# テスト対象のインポートパス解決
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from helper.helper_llm import (
    AnthropicClient,
    GeminiClient,
    OpenAIClient,
    create_llm_client,
)


# テスト用Pydanticモデル
class MockResponseSchema(BaseModel):
    message: str
    score: int

class QAPair(BaseModel):
    question: str
    answer: str

class QAPairsResponse(BaseModel):
    qa_pairs: List[QAPair]

# ====================================
# ファクトリ関数テスト
# ====================================

class TestCreateLLMClient:
    def test_create_gemini_client(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            # GeminiClient は google-genai を遅延 import するため google.genai.Client を patch
            with patch("google.genai.Client"):
                client = create_llm_client("gemini")
                assert isinstance(client, GeminiClient)

    def test_create_openai_client(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("helper.helper_llm.OpenAI"):
                client = create_llm_client("openai")
                assert isinstance(client, OpenAIClient)

    def test_invalid_provider(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
             with patch("google.genai.Client"):
                client = create_llm_client("invalid_provider")
                assert isinstance(client, GeminiClient)

# ====================================
# OpenAIClient テスト
# ====================================

class TestOpenAIClient:
    @pytest.fixture
    def mock_openai_client(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("helper.helper_llm.OpenAI") as mock_class:
                mock_instance = Mock()
                mock_class.return_value = mock_instance
                client = OpenAIClient()
                return client, mock_instance

    def test_generate_content(self, mock_openai_client):
        client, mock_instance = mock_openai_client
        mock_response = Mock()
        mock_response.output_text = "Hello, world!"
        mock_response.usage = None
        mock_instance.responses.create.return_value = mock_response

        result = client.generate_content("Say hello")
        assert result == "Hello, world!"

    def test_generate_content_with_system_instruction(self, mock_openai_client):
        client, mock_instance = mock_openai_client
        mock_response = Mock()
        mock_response.output_text = "Response"
        mock_response.usage = None
        mock_instance.responses.create.return_value = mock_response
        
        client.generate_content("Question", max_tokens=123, temperature=0.7)
        call_args = mock_instance.responses.create.call_args
        assert call_args.kwargs["max_output_tokens"] == 123
        assert "temperature" not in call_args.kwargs

    def test_generate_structured(self, mock_openai_client):
        client, mock_instance = mock_openai_client
        mock_response = Mock()
        mock_response.output_parsed = MockResponseSchema(message="test", score=100)
        mock_response.usage = None
        mock_instance.responses.parse.return_value = mock_response

        result = client.generate_structured("Generate test", MockResponseSchema)
        assert result.message == "test"
        assert result.score == 100
        assert mock_instance.responses.parse.call_args.kwargs["text_format"] is MockResponseSchema

    def test_count_tokens(self, mock_openai_client):
        client, _ = mock_openai_client
        with patch("helper.helper_llm.tiktoken") as mock_tiktoken:
            mock_encoding = Mock()
            mock_encoding.encode.return_value = [1, 2, 3, 4, 5]
            mock_tiktoken.encoding_for_model.return_value = mock_encoding
            mock_tiktoken.get_encoding.return_value = mock_encoding

            count = client.count_tokens("Hello world")
            assert count == 5

    def test_generate_with_tools_uses_responses_function_calling(self, mock_openai_client):
        client, mock_instance = mock_openai_client
        mock_instance.responses.create.return_value = SimpleNamespace(
            output=[SimpleNamespace(
                type="function_call",
                name="search",
                arguments='{"query":"news"}',
                call_id="call_1",
            )],
            output_text="",
            usage=SimpleNamespace(input_tokens=4, output_tokens=2),
        )

        result = client.generate_with_tools(
            messages=[{"role": "user", "content": "search news"}],
            tools=[{
                "name": "search",
                "description": "search",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }],
            system="system",
        )

        assert result.stop_reason == "tool_use"
        assert result.tool_calls == [
            {"name": "search", "input": {"query": "news"}, "id": "call_1"}
        ]
        call = mock_instance.responses.create.call_args.kwargs
        assert call["tools"][0]["type"] == "function"
        assert call["tools"][0]["parameters"]["required"] == ["query"]

    def test_tool_result_is_converted_to_function_call_output(self, mock_openai_client):
        client, mock_instance = mock_openai_client
        mock_instance.responses.create.return_value = SimpleNamespace(
            output=[], output_text="done", usage=None,
        )
        client.generate_with_tools(
            messages=[{
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "call_1",
                    "content": "result",
                }],
            }],
            tools=[],
        )
        assert mock_instance.responses.create.call_args.kwargs["input"] == [{
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "result",
        }]

# ====================================
# GeminiClient テスト
# ====================================

class TestGeminiClient:

    @pytest.fixture
    def mock_gemini_client(self):
        # 新SDK (google-genai) では genai.Client(api_key=...) を生成し、
        # client.models.generate_content / count_tokens を呼び出す。
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            # GeminiClient は google-genai を遅延 import するため google.genai.Client を patch
            with patch("google.genai.Client") as mock_client_cls:
                # genai.Client() が返すクライアントインスタンス
                mock_client_instance = Mock()
                mock_client_cls.return_value = mock_client_instance

                client = GeminiClient()
                # テストからは client.models をモックとして触れるよう返す
                yield client, mock_client_instance.models

    def test_generate_content(self, mock_gemini_client):
        client, mock_models = mock_gemini_client

        mock_response = Mock()
        mock_response.text = "こんにちは"
        mock_models.generate_content.return_value = mock_response

        result = client.generate_content("Hello")
        assert result == "こんにちは"

    def test_generate_content_with_kwargs(self, mock_gemini_client):
        client, mock_models = mock_gemini_client

        mock_response = Mock()
        mock_response.text = "Response"
        mock_models.generate_content.return_value = mock_response

        # 新SDKでは temperature/max_output_tokens は config 経由で渡される
        client.generate_content("Question", temperature=0.5, max_output_tokens=128)

        args, kwargs = mock_models.generate_content.call_args
        assert kwargs["contents"] == "Question"
        # config は types.GenerateContentConfig インスタンス
        assert kwargs["config"].temperature == 0.5
        assert kwargs["config"].max_output_tokens == 128

    def test_generate_structured(self, mock_gemini_client):
        client, mock_models = mock_gemini_client

        mock_response = Mock()
        mock_response.text = '{"message": "test", "score": 100}'
        mock_models.generate_content.return_value = mock_response

        result = client.generate_structured("Generate", MockResponseSchema)
        assert result.message == "test"
        assert result.score == 100

    def test_generate_structured_invalid_json(self, mock_gemini_client):
        client, mock_models = mock_gemini_client

        mock_response = Mock()
        mock_response.text = "not valid json"
        mock_models.generate_content.return_value = mock_response

        with pytest.raises(Exception):
            client.generate_structured("Generate", MockResponseSchema)

    def test_count_tokens(self, mock_gemini_client):
        client, mock_models = mock_gemini_client

        mock_response = Mock()
        mock_response.total_tokens = 10
        mock_models.count_tokens.return_value = mock_response

        count = client.count_tokens("Hello world")
        assert count == 10


# AnthropicClient テスト（per-call usage 配管）
class TestAnthropicClient:
    def _client_with_message(self, text="hi", input_tokens=11, output_tokens=22):
        """messages.create が usage 付き message を返す AnthropicClient を作る。"""
        client = AnthropicClient(api_key="dummy")
        msg = Mock()
        block = Mock()
        block.text = text
        msg.content = [block]
        usage = Mock()
        usage.input_tokens = input_tokens
        usage.output_tokens = output_tokens
        msg.usage = usage
        sdk = Mock()
        sdk.messages.create.return_value = msg
        # 遅延初期化された SDK クライアントを差し替え
        client._client = sdk
        return client

    def test_generate_content_records_usage(self):
        client = self._client_with_message(text="answer", input_tokens=100, output_tokens=40)
        out = client.generate_content("質問", model="claude-sonnet-4-6")
        assert out == "answer"
        assert client.last_usage == {"input_tokens": 100, "output_tokens": 40}

    def test_initial_usage_is_zero(self):
        client = AnthropicClient(api_key="dummy")
        assert client.last_usage == {"input_tokens": 0, "output_tokens": 0}

    def test_missing_usage_defaults_zero(self):
        client = AnthropicClient(api_key="dummy")
        msg = Mock()
        block = Mock()
        block.text = "x"
        msg.content = [block]
        msg.usage = None  # usage 欠落
        sdk = Mock()
        sdk.messages.create.return_value = msg
        client._client = sdk
        client.generate_content("q")
        assert client.last_usage == {"input_tokens": 0, "output_tokens": 0}
