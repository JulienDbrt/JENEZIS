"""
Unit Tests for Extractor - Entity and Relation Extraction

Targets: jenezis/ingestion/extractor.py
Coverage: 28% -> 80%+
"""
import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch

from jenezis.ingestion.extractor import (
    Extractor,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
    _create_dynamic_prompt,
    get_extractor,
)

pytestmark = pytest.mark.unit


class TestCreateDynamicPrompt:
    """Tests for _create_dynamic_prompt function."""

    def test_creates_prompt_with_entity_types(self):
        """Prompt includes entity types."""
        schema = {
            "entity_types": ["Person", "Organization"],
            "relation_types": ["WORKS_FOR"]
        }

        prompt = _create_dynamic_prompt(schema)

        assert "Person" in prompt
        assert "Organization" in prompt

    def test_creates_prompt_with_relation_types(self):
        """Prompt includes relation types."""
        schema = {
            "entity_types": ["Person"],
            "relation_types": ["WORKS_FOR", "OWNS"]
        }

        prompt = _create_dynamic_prompt(schema)

        assert "WORKS_FOR" in prompt
        assert "OWNS" in prompt

    def test_empty_entity_types_returns_empty(self):
        """Empty entity types returns empty prompt."""
        schema = {"entity_types": [], "relation_types": ["WORKS_FOR"]}

        prompt = _create_dynamic_prompt(schema)

        assert prompt == ""

    def test_empty_relation_types_shows_none(self):
        """Empty relation types shows NONE."""
        schema = {"entity_types": ["Person"], "relation_types": []}

        prompt = _create_dynamic_prompt(schema)

        assert "NONE" in prompt

    def test_sanitizes_malicious_types(self):
        """Malicious type names are sanitized."""
        schema = {
            "entity_types": ["Person<script>"],
            "relation_types": ["WORKS;DROP TABLE"]
        }

        prompt = _create_dynamic_prompt(schema)

        assert "<script>" not in prompt


class TestExtractionModels:
    """Tests for Pydantic extraction models."""

    def test_extracted_entity_valid(self):
        """ExtractedEntity validates correctly."""
        entity = ExtractedEntity(id="JOHN_DOE", name="John Doe", type="Person")

        assert entity.id == "JOHN_DOE"
        assert entity.name == "John Doe"
        assert entity.type == "Person"

    def test_extracted_relation_valid(self):
        """ExtractedRelation validates correctly."""
        relation = ExtractedRelation(source="E1", target="E2", type="WORKS_FOR")

        assert relation.source == "E1"
        assert relation.target == "E2"
        assert relation.type == "WORKS_FOR"

    def test_extraction_result_valid(self):
        """ExtractionResult validates correctly."""
        result = ExtractionResult(
            entities=[
                ExtractedEntity(id="E1", name="Test", type="Person")
            ],
            relations=[
                ExtractedRelation(source="E1", target="E1", type="SELF")
            ]
        )

        assert len(result.entities) == 1
        assert len(result.relations) == 1

    def test_extraction_result_from_json(self):
        """ExtractionResult parses from JSON."""
        json_str = json.dumps({
            "entities": [{"id": "E1", "name": "Test", "type": "Person"}],
            "relations": []
        })

        result = ExtractionResult.model_validate_json(json_str)

        assert len(result.entities) == 1


class TestExtractorInit:
    """Tests for Extractor initialization."""

    @patch("jenezis.ingestion.extractor.openai.AsyncOpenAI")
    @patch("jenezis.ingestion.extractor.settings")
    def test_init_openai_provider(self, mock_settings, mock_openai):
        """Extractor initializes with OpenAI provider."""
        mock_settings.LLM_PROVIDER = "openai"
        mock_settings.EXTRACTION_MODEL = "gpt-3.5-turbo"
        mock_settings.OPENAI_API_KEY = "test-key"

        extractor = Extractor()

        mock_openai.assert_called_once_with(api_key="test-key")
        assert extractor.model == "gpt-3.5-turbo"

    @patch("jenezis.ingestion.extractor.openai.AsyncOpenAI")
    @patch("jenezis.ingestion.extractor.settings")
    def test_init_openrouter_provider(self, mock_settings, mock_openai):
        """Extractor initializes with OpenRouter provider."""
        mock_settings.LLM_PROVIDER = "openrouter"
        mock_settings.EXTRACTION_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "or-key"

        extractor = Extractor()

        call_kwargs = mock_openai.call_args.kwargs
        assert "openrouter.ai" in call_kwargs["base_url"]

    @patch("jenezis.ingestion.extractor.settings")
    def test_init_anthropic_raises(self, mock_settings):
        """Extractor raises for Anthropic (not implemented)."""
        mock_settings.LLM_PROVIDER = "anthropic"

        with pytest.raises(NotImplementedError, match="Anthropic"):
            Extractor()

    @patch("jenezis.ingestion.extractor.settings")
    def test_init_invalid_provider_raises(self, mock_settings):
        """Extractor raises for unknown provider."""
        mock_settings.LLM_PROVIDER = "unknown"

        with pytest.raises(ValueError, match="Unsupported"):
            Extractor()


class TestExtractFromChunk:
    """Tests for extract_from_chunk method."""

    @pytest.fixture
    def extractor(self):
        """Create extractor with mocked client."""
        with patch("jenezis.ingestion.extractor.openai.AsyncOpenAI") as mock_openai:
            with patch("jenezis.ingestion.extractor.settings") as mock_settings:
                mock_settings.LLM_PROVIDER = "openai"
                mock_settings.EXTRACTION_MODEL = "gpt-3.5-turbo"
                mock_settings.OPENAI_API_KEY = "test-key"

                mock_client = MagicMock()
                mock_openai.return_value = mock_client

                ext = Extractor()
                ext.client = mock_client
                return ext

    async def test_extract_empty_text_returns_empty(self, extractor):
        """Empty text returns empty result."""
        result = await extractor.extract_from_chunk("", {"entity_types": ["Person"]})

        assert result.entities == []
        assert result.relations == []

    async def test_extract_empty_schema_returns_empty(self, extractor):
        """Empty schema returns empty result."""
        result = await extractor.extract_from_chunk("Some text", {})

        assert result.entities == []
        assert result.relations == []

    async def test_extract_no_entity_types_returns_empty(self, extractor):
        """Schema without entity types returns empty."""
        result = await extractor.extract_from_chunk(
            "Some text",
            {"entity_types": [], "relation_types": ["WORKS_FOR"]}
        )

        assert result.entities == []

    async def test_extract_success(self, extractor):
        """Successful extraction returns entities and relations."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "entities": [{"id": "JOHN", "name": "John", "type": "Person"}],
            "relations": [{"source": "JOHN", "target": "JOHN", "type": "KNOWS"}]
        })
        extractor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await extractor.extract_from_chunk(
            "John knows himself.",
            {"entity_types": ["Person"], "relation_types": ["KNOWS"]}
        )

        assert len(result.entities) == 1
        assert result.entities[0].id == "JOHN"

    async def test_extract_error_returns_empty(self, extractor):
        """API error returns empty result."""
        extractor.client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        result = await extractor.extract_from_chunk(
            "Some text",
            {"entity_types": ["Person"], "relation_types": []}
        )

        assert result.entities == []
        assert result.relations == []


class TestExtractFromAllChunks:
    """Tests for extract_from_all_chunks method."""

    @pytest.fixture
    def extractor(self):
        """Create extractor with mocked client."""
        with patch("jenezis.ingestion.extractor.openai.AsyncOpenAI") as mock_openai:
            with patch("jenezis.ingestion.extractor.settings") as mock_settings:
                mock_settings.LLM_PROVIDER = "openai"
                mock_settings.EXTRACTION_MODEL = "gpt-3.5-turbo"
                mock_settings.OPENAI_API_KEY = "test-key"

                mock_client = MagicMock()
                mock_openai.return_value = mock_client

                ext = Extractor()
                ext.client = mock_client
                return ext

    async def test_extract_all_empty_schema(self, extractor):
        """Empty schema returns empty lists."""
        entities, relations = await extractor.extract_from_all_chunks(
            [{"id": "c1", "text": "Hello"}],
            {}
        )

        assert entities == []
        assert relations == []

    async def test_extract_all_combines_results(self, extractor):
        """Results from multiple chunks are combined."""
        # Mock extract_from_chunk to return different results
        call_count = 0

        async def mock_extract(text, schema):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ExtractionResult(
                    entities=[ExtractedEntity(id="E1", name="Entity1", type="Person")],
                    relations=[]
                )
            else:
                return ExtractionResult(
                    entities=[ExtractedEntity(id="E2", name="Entity2", type="Person")],
                    relations=[ExtractedRelation(source="E1", target="E2", type="KNOWS")]
                )

        extractor.extract_from_chunk = mock_extract

        chunks = [
            {"id": "c1", "text": "Chunk 1"},
            {"id": "c2", "text": "Chunk 2"}
        ]

        entities, relations = await extractor.extract_from_all_chunks(
            chunks,
            {"entity_types": ["Person"], "relation_types": ["KNOWS"]}
        )

        assert len(entities) == 2
        assert len(relations) == 1
        assert relations[0]["chunk_id"] == "c2"

    async def test_extract_all_deduplicates_entities(self, extractor):
        """Duplicate entities are deduplicated."""
        async def mock_extract(text, schema):
            return ExtractionResult(
                entities=[ExtractedEntity(id="SAME", name="Same", type="Person")],
                relations=[]
            )

        extractor.extract_from_chunk = mock_extract

        chunks = [
            {"id": "c1", "text": "Chunk 1"},
            {"id": "c2", "text": "Chunk 2"}
        ]

        entities, _ = await extractor.extract_from_all_chunks(
            chunks,
            {"entity_types": ["Person"]}
        )

        # Should be deduplicated to 1
        assert len(entities) == 1


class TestGetExtractor:
    """Tests for factory function."""

    @patch("jenezis.ingestion.extractor.Extractor")
    def test_get_extractor_returns_instance(self, mock_extractor_class):
        """Factory returns Extractor instance."""
        mock_extractor_class.return_value = MagicMock()

        result = get_extractor()

        mock_extractor_class.assert_called_once()
