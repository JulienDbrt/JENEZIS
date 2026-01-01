"""
Unit Tests for Validator - Ontology Conformance Filtering

Targets: jenezis/ingestion/validator.py
Coverage: 0% -> 100%
"""
import pytest
from jenezis.ingestion.validator import Validator

pytestmark = pytest.mark.unit


class TestValidatorInit:
    """Tests for Validator initialization."""

    def test_init_with_valid_schema(self):
        """Validator initializes with valid ontology schema."""
        schema = {
            "entity_types": ["Person", "Organization"],
            "relation_types": ["WORKS_FOR", "OWNS"]
        }
        validator = Validator(schema)

        assert validator.ontology_schema == schema
        assert validator.valid_entity_types == {"Person", "Organization"}
        assert validator.valid_relation_types == {"WORKS_FOR", "OWNS"}

    def test_init_with_empty_schema(self):
        """Validator initializes with empty schema."""
        validator = Validator({})

        assert validator.valid_entity_types == set()
        assert validator.valid_relation_types == set()

    def test_init_with_missing_keys(self):
        """Validator handles schema with missing keys gracefully."""
        schema = {"entity_types": ["Risk"]}
        validator = Validator(schema)

        assert validator.valid_entity_types == {"Risk"}
        assert validator.valid_relation_types == set()


class TestValidateAndFilter:
    """Tests for validate_and_filter method."""

    @pytest.fixture
    def validator(self):
        """Standard validator for testing."""
        return Validator({
            "entity_types": ["Person", "Organization", "Risk"],
            "relation_types": ["WORKS_FOR", "MITIGATES"]
        })

    def test_valid_entities_pass_through(self, validator):
        """Valid entities are preserved."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Acme", "type": "Organization"}
        ]
        relations = []

        valid_entities, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_entities) == 2
        assert valid_entities[0]["id"] == "e1"
        assert valid_entities[1]["id"] == "e2"

    def test_invalid_entity_types_filtered(self, validator):
        """Entities with invalid types are filtered out."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Money", "type": "Currency"},  # Invalid
            {"id": "e3", "name": "Fraud", "type": "Risk"}
        ]
        relations = []

        valid_entities, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_entities) == 2
        assert all(e["type"] in ["Person", "Risk"] for e in valid_entities)

    def test_valid_relations_pass_through(self, validator):
        """Valid relations between valid entities are preserved."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Acme", "type": "Organization"}
        ]
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR"}
        ]

        valid_entities, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_relations) == 1
        assert valid_relations[0]["type"] == "WORKS_FOR"

    def test_invalid_relation_types_filtered(self, validator):
        """Relations with invalid types are filtered out."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Acme", "type": "Organization"}
        ]
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR"},
            {"source_id": "e1", "target_id": "e2", "type": "LOVES"}  # Invalid
        ]

        valid_entities, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_relations) == 1
        assert valid_relations[0]["type"] == "WORKS_FOR"

    def test_relations_with_invalid_entities_filtered(self, validator):
        """Relations referencing invalid/filtered entities are removed."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Money", "type": "Currency"}  # Will be filtered
        ]
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR"}  # Invalid target
        ]

        valid_entities, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_entities) == 1
        assert len(valid_relations) == 0  # Relation removed because e2 was filtered

    def test_empty_input(self, validator):
        """Empty input returns empty output."""
        valid_entities, valid_relations = validator.validate_and_filter([], [])

        assert valid_entities == []
        assert valid_relations == []

    def test_no_ontology_passes_all(self):
        """Empty ontology passes through all data."""
        validator = Validator({})
        entities = [
            {"id": "e1", "name": "Anything", "type": "Whatever"}
        ]
        relations = [
            {"source_id": "e1", "target_id": "e1", "type": "SELF_REF"}
        ]

        valid_entities, valid_relations = validator.validate_and_filter(entities, relations)

        # With empty schema, everything passes through
        assert len(valid_entities) == 1
        assert len(valid_relations) == 1

    def test_entity_without_type_filtered(self, validator):
        """Entities without type field are filtered."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "NoType"}  # Missing type
        ]

        valid_entities, _ = validator.validate_and_filter(entities, [])

        assert len(valid_entities) == 1
        assert valid_entities[0]["id"] == "e1"

    def test_relation_missing_source_filtered(self, validator):
        """Relations with missing source_id are filtered."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Acme", "type": "Organization"}
        ]
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR"},
            {"target_id": "e2", "type": "WORKS_FOR"}  # Missing source_id
        ]

        _, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_relations) == 1

    def test_relation_missing_target_filtered(self, validator):
        """Relations with missing target_id are filtered."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Acme", "type": "Organization"}
        ]
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR"},
            {"source_id": "e1", "type": "WORKS_FOR"}  # Missing target_id
        ]

        _, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_relations) == 1

    def test_case_sensitive_entity_types(self, validator):
        """Entity type matching is case-sensitive."""
        entities = [
            {"id": "e1", "name": "John", "type": "person"},  # lowercase - invalid
            {"id": "e2", "name": "Jane", "type": "Person"}   # correct case
        ]

        valid_entities, _ = validator.validate_and_filter(entities, [])

        assert len(valid_entities) == 1
        assert valid_entities[0]["id"] == "e2"

    def test_case_sensitive_relation_types(self, validator):
        """Relation type matching is case-sensitive."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Acme", "type": "Organization"}
        ]
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "works_for"},  # lowercase
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR"}   # correct
        ]

        _, valid_relations = validator.validate_and_filter(entities, relations)

        assert len(valid_relations) == 1
        assert valid_relations[0]["type"] == "WORKS_FOR"


class TestValidatorLogging:
    """Tests for validator logging behavior."""

    def test_logs_warning_on_filtered_entities(self, caplog):
        """Validator logs warning when filtering entities."""
        validator = Validator({"entity_types": ["Person"]})
        entities = [
            {"id": "e1", "name": "John", "type": "Invalid"}
        ]

        with caplog.at_level("WARNING"):
            validator.validate_and_filter(entities, [])

        assert "Filtered out 1 entities" in caplog.text

    def test_logs_warning_on_filtered_relations(self, caplog):
        """Validator logs warning when filtering relations."""
        validator = Validator({
            "entity_types": ["Person"],
            "relation_types": ["VALID"]
        })
        entities = [{"id": "e1", "name": "John", "type": "Person"}]
        relations = [{"source_id": "e1", "target_id": "e1", "type": "INVALID"}]

        with caplog.at_level("WARNING"):
            validator.validate_and_filter(entities, relations)

        assert "Filtered out 1 relations" in caplog.text

    def test_logs_warning_on_empty_schema(self, caplog):
        """Validator logs warning when schema is empty."""
        validator = Validator({})
        entities = [{"id": "e1", "name": "Test", "type": "Any"}]

        with caplog.at_level("WARNING"):
            validator.validate_and_filter(entities, [])

        assert "no ontology schema" in caplog.text
