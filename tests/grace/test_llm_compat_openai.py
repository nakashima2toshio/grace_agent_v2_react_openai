from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import BaseModel

from grace.config import GraceConfig
from grace.llm_compat import OpenAIGenaiClient, create_chat_client


class ParsedAnswer(BaseModel):
    answer: str


def test_create_chat_client_defaults_to_openai():
    client = create_chat_client(GraceConfig())
    assert isinstance(client, OpenAIGenaiClient)


def test_generate_content_uses_responses_create():
    sdk = Mock()
    sdk.responses.create.return_value = SimpleNamespace(
        output_text="answer",
        usage=SimpleNamespace(input_tokens=3, output_tokens=2),
    )
    client = OpenAIGenaiClient("gpt-5-mini")
    client._client = sdk

    response = client.models.generate_content(
        contents="question",
        config={"max_output_tokens": 123, "temperature": 0.7},
    )

    assert response.text == "answer"
    assert response.usage_metadata.prompt_token_count == 3
    sdk.responses.create.assert_called_once_with(
        model="gpt-5-mini", input="question", max_output_tokens=123
    )


def test_generate_content_uses_responses_parse_for_pydantic_schema():
    sdk = Mock()
    parsed = ParsedAnswer(answer="structured")
    sdk.responses.parse.return_value = SimpleNamespace(
        output_parsed=parsed,
        output_text='{"answer":"structured"}',
        usage=None,
    )
    client = OpenAIGenaiClient("gpt-5-mini")
    client._client = sdk

    response = client.models.generate_content(
        contents="question",
        config={"response_schema": ParsedAnswer},
    )

    assert response.parsed == parsed
    assert response.text == parsed.model_dump_json()
    assert sdk.responses.parse.call_args.kwargs["text_format"] is ParsedAnswer


def test_openai_client_is_lazy():
    with patch("openai.OpenAI") as constructor:
        OpenAIGenaiClient("gpt-5-mini")
    constructor.assert_not_called()
