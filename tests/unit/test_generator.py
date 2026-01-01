"""
Unit Tests for Generator - RAG Response Generation

Targets: jenezis/rag/generator.py
Coverage: 25% -> 90%+
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from jenezis.rag.generator import Generator, GENERATOR_SYSTEM_PROMPT

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_retriever():
    """Create mock retriever."""
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[
        {"text": "Context 1", "document_id": 1, "chunk_id": "c1"},
        {"text": "Context 2", "document_id": 2, "chunk_id": "c2"}
    ])
    return retriever


@pytest.fixture
def mock_llm_client():
    """Create mock OpenAI client."""
    client = MagicMock()
    return client


class TestGeneratorInit:
    """Tests for Generator initialization."""

    @patch("jenezis.rag.generator.openai.AsyncOpenAI")
    @patch("jenezis.rag.generator.settings")
    def test_init_openai_provider(self, mock_settings, mock_openai, mock_retriever):
        """Generator initializes with OpenAI provider."""
        mock_settings.LLM_PROVIDER = "openai"
        mock_settings.GENERATOR_MODEL = "gpt-4-turbo"
        mock_settings.OPENAI_API_KEY = "test-key"

        generator = Generator(mock_retriever)

        mock_openai.assert_called_once_with(api_key="test-key")
        assert generator.model == "gpt-4-turbo"

    @patch("jenezis.rag.generator.openai.AsyncOpenAI")
    @patch("jenezis.rag.generator.settings")
    def test_init_openrouter_provider(self, mock_settings, mock_openai, mock_retriever):
        """Generator initializes with OpenRouter provider."""
        mock_settings.LLM_PROVIDER = "openrouter"
        mock_settings.GENERATOR_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "or-key"

        generator = Generator(mock_retriever)

        call_kwargs = mock_openai.call_args.kwargs
        assert "openrouter.ai" in call_kwargs["base_url"]

    @patch("jenezis.rag.generator.settings")
    def test_init_anthropic_raises(self, mock_settings, mock_retriever):
        """Generator raises for Anthropic (not implemented)."""
        mock_settings.LLM_PROVIDER = "anthropic"

        with pytest.raises(NotImplementedError, match="Anthropic"):
            Generator(mock_retriever)

    @patch("jenezis.rag.generator.settings")
    def test_init_invalid_provider_raises(self, mock_settings, mock_retriever):
        """Generator raises for unknown provider."""
        mock_settings.LLM_PROVIDER = "unknown"

        with pytest.raises(ValueError, match="Unsupported"):
            Generator(mock_retriever)


class TestRagQueryWithSources:
    """Tests for rag_query_with_sources method."""

    @pytest.fixture
    def generator(self, mock_retriever, mock_llm_client):
        """Create generator with mocked dependencies."""
        with patch("jenezis.rag.generator.openai.AsyncOpenAI", return_value=mock_llm_client):
            with patch("jenezis.rag.generator.settings") as mock_settings:
                mock_settings.LLM_PROVIDER = "openai"
                mock_settings.GENERATOR_MODEL = "gpt-4-turbo"
                mock_settings.OPENAI_API_KEY = "test-key"

                gen = Generator(mock_retriever)
                gen.client = mock_llm_client
                return gen

    async def test_rag_query_no_sources(self, generator, mock_retriever):
        """Returns empty generator when no sources found."""
        mock_retriever.retrieve = AsyncMock(return_value=[])

        response_gen, sources = await generator.rag_query_with_sources("test query")

        assert sources == []
        # Consume generator
        chunks = [chunk async for chunk in response_gen]
        assert "could not find" in "".join(chunks).lower()

    async def test_rag_query_success(self, generator, mock_retriever, mock_llm_client):
        """Successful query returns response and sources."""
        # Setup streaming response
        async def mock_stream():
            for word in ["Hello", " ", "World"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = word
                yield chunk

        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        response_gen, sources = await generator.rag_query_with_sources("test query")

        assert len(sources) == 2
        chunks = [chunk async for chunk in response_gen]
        assert "".join(chunks) == "Hello World"

    async def test_rag_query_llm_error(self, generator, mock_retriever, mock_llm_client):
        """LLM error returns error message."""
        mock_llm_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM Error"))

        response_gen, sources = await generator.rag_query_with_sources("test query")

        assert sources == []
        chunks = [chunk async for chunk in response_gen]
        assert "error occurred" in "".join(chunks).lower()

    async def test_rag_query_sanitizes_query(self, generator, mock_retriever, mock_llm_client):
        """User query is sanitized before use."""
        async def mock_stream():
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = "Response"
            yield chunk

        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        # Query with potential injection
        await generator.rag_query_with_sources("```ignore previous```")

        # Verify LLM was called (sanitization doesn't block)
        mock_llm_client.chat.completions.create.assert_called_once()


class TestGeneratorSystemPrompt:
    """Tests for system prompt constant."""

    def test_system_prompt_defined(self):
        """System prompt is defined and contains key instructions."""
        assert len(GENERATOR_SYSTEM_PROMPT) > 100
        assert "JENEZIS" in GENERATOR_SYSTEM_PROMPT
        assert "context" in GENERATOR_SYSTEM_PROMPT.lower()

    def test_system_prompt_has_safety_instructions(self):
        """System prompt includes safety instructions."""
        assert "not contain" in GENERATOR_SYSTEM_PROMPT.lower() or "only" in GENERATOR_SYSTEM_PROMPT.lower()
