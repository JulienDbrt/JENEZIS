"""
Unit Tests for Embedder - Text Embedding Generation

Targets: jenezis/ingestion/embedder.py
Coverage: 26% -> 90%+
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

pytestmark = pytest.mark.unit


class TestEmbedderInit:
    """Tests for Embedder initialization."""

    @patch("jenezis.ingestion.embedder.openai.AsyncOpenAI")
    @patch("jenezis.ingestion.embedder.settings")
    def test_init_openai_provider(self, mock_settings, mock_openai):
        """Embedder initializes with OpenAI provider."""
        mock_settings.LLM_PROVIDER = "openai"
        mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
        mock_settings.EMBEDDING_BATCH_SIZE = 128
        mock_settings.OPENAI_API_KEY = "test-key"

        from jenezis.ingestion.embedder import Embedder
        embedder = Embedder()

        mock_openai.assert_called_once_with(api_key="test-key")
        assert embedder.model == "text-embedding-3-small"

    @patch("jenezis.ingestion.embedder.openai.AsyncOpenAI")
    @patch("jenezis.ingestion.embedder.settings")
    def test_init_openrouter_provider(self, mock_settings, mock_openai):
        """Embedder initializes with OpenRouter provider."""
        mock_settings.LLM_PROVIDER = "openrouter"
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_BATCH_SIZE = 64
        mock_settings.OPENROUTER_API_KEY = "or-key"

        from jenezis.ingestion.embedder import Embedder
        embedder = Embedder()

        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args.kwargs
        assert "openrouter.ai" in call_kwargs["base_url"]

    @patch("jenezis.ingestion.embedder.settings")
    def test_init_anthropic_raises(self, mock_settings):
        """Embedder raises for Anthropic (no embedding API)."""
        mock_settings.LLM_PROVIDER = "anthropic"

        from jenezis.ingestion.embedder import Embedder
        with pytest.raises(NotImplementedError, match="Anthropic"):
            Embedder()

    @patch("jenezis.ingestion.embedder.settings")
    def test_init_invalid_provider_raises(self, mock_settings):
        """Embedder raises for unknown provider."""
        mock_settings.LLM_PROVIDER = "unknown"

        from jenezis.ingestion.embedder import Embedder
        with pytest.raises(ValueError, match="Unsupported"):
            Embedder()


class TestEmbedBatch:
    """Tests for embed_batch method."""

    @pytest.fixture
    def embedder(self):
        """Create embedder with mocked client."""
        with patch("jenezis.ingestion.embedder.openai.AsyncOpenAI") as mock_openai:
            with patch("jenezis.ingestion.embedder.settings") as mock_settings:
                mock_settings.LLM_PROVIDER = "openai"
                mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
                mock_settings.EMBEDDING_BATCH_SIZE = 128
                mock_settings.OPENAI_API_KEY = "test-key"
                mock_settings.EMBEDDING_DIMENSIONS = 1536

                mock_client = MagicMock()
                mock_openai.return_value = mock_client

                from jenezis.ingestion.embedder import Embedder
                emb = Embedder()
                emb.client = mock_client
                return emb

    async def test_embed_batch_empty_returns_empty(self, embedder):
        """Empty input returns empty list."""
        result = await embedder.embed_batch([])
        assert result == []

    async def test_embed_batch_success(self, embedder):
        """Successful embedding returns vectors."""
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2, 0.3]),
            MagicMock(embedding=[0.4, 0.5, 0.6])
        ]
        embedder.client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await embedder.embed_batch(["text1", "text2"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    async def test_embed_batch_replaces_newlines(self, embedder):
        """Newlines are replaced with spaces."""
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1])]
        embedder.client.embeddings.create = AsyncMock(return_value=mock_response)

        await embedder.embed_batch(["line1\nline2\nline3"])

        call_kwargs = embedder.client.embeddings.create.call_args.kwargs
        assert "\n" not in call_kwargs["input"][0]
        assert "line1 line2 line3" == call_kwargs["input"][0]

    async def test_embed_batch_error_raises(self, embedder):
        """API error is raised."""
        embedder.client.embeddings.create = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(Exception, match="API Error"):
            await embedder.embed_batch(["test"])


class TestEmbedAll:
    """Tests for embed_all method with batching."""

    @pytest.fixture
    def embedder(self):
        """Create embedder with mocked client."""
        with patch("jenezis.ingestion.embedder.openai.AsyncOpenAI") as mock_openai:
            with patch("jenezis.ingestion.embedder.settings") as mock_settings:
                mock_settings.LLM_PROVIDER = "openai"
                mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
                mock_settings.EMBEDDING_BATCH_SIZE = 2  # Small batch for testing
                mock_settings.OPENAI_API_KEY = "test-key"
                mock_settings.EMBEDDING_DIMENSIONS = 1536

                mock_client = MagicMock()
                mock_openai.return_value = mock_client

                from jenezis.ingestion.embedder import Embedder
                emb = Embedder()
                emb.client = mock_client
                return emb

    async def test_embed_all_batches_correctly(self, embedder):
        """Large input is batched correctly."""
        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * len(kwargs["input"]))]
            return mock_response

        embedder.client.embeddings.create = mock_create

        # With batch_size=2, 5 texts should make 3 batches
        texts = ["t1", "t2", "t3", "t4", "t5"]
        result = await embedder.embed_all(texts)

        assert call_count == 3  # 2 + 2 + 1


class TestGetEmbedder:
    """Tests for factory function."""

    @patch("jenezis.ingestion.embedder.Embedder")
    def test_get_embedder_returns_instance(self, mock_embedder_class):
        """Factory returns Embedder instance."""
        mock_embedder_class.return_value = MagicMock()

        from jenezis.ingestion.embedder import get_embedder
        result = get_embedder()

        mock_embedder_class.assert_called_once()
