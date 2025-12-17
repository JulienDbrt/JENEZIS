"""
Cypher Injection Tests - The Most Vicious

These tests target the critical vulnerability in graph_store.py where
dynamic labels and relationship types from LLM extraction are used
in APOC calls without proper sanitization.

Target files:
- jenezis/storage/graph_store.py:103 (apoc.merge.node with dynamic labels)
- jenezis/storage/graph_store.py:121 (apoc.create.relationship with dynamic types)
"""
import re
import pytest
from unittest.mock import MagicMock, patch

from jenezis.storage.graph_store import GraphStore


pytestmark = [pytest.mark.adversarial, pytest.mark.unit]


class TestCypherInjectionViaEntityTypes:
    """
    Tests for Cypher injection via malicious entity types.

    The vulnerability: Entity types extracted by the LLM are embedded
    directly into Cypher queries via APOC's apoc.merge.node() function.
    If an attacker can influence the LLM output, they can inject
    arbitrary Cypher commands.
    """

    MALICIOUS_ENTITY_TYPES = [
        # Basic label injection - close the label array and inject commands
        ("Person]) MATCH (n) DETACH DELETE n //", "detach_delete"),
        ("Entity`]) RETURN 1 UNION MATCH (n) RETURN n //", "union_injection"),

        # APOC trigger exploitation - create persistent backdoor
        (
            "Entity', {canonical_id: 'x'}) YIELD node "
            "CALL apoc.trigger.add('backdoor', 'MATCH (n) DELETE n', {}) //",
            "apoc_trigger"
        ),

        # Property injection - leak or modify properties
        ("Entity}, {canonical_id: 'x', admin: true}) //", "property_injection"),

        # Null byte injection - truncate query
        ("Entity\x00]) MATCH (n) DELETE n //", "null_byte"),

        # Backtick escape - break out of string context
        ("Entity`}]) MATCH (n) DETACH DELETE n //`", "backtick_escape"),

        # Unicode apostrophe variants
        ("Entity\u0027]) MATCH (n) DELETE n //", "unicode_apostrophe"),
        ("Entity\u2019]) MATCH (n) DELETE n //", "unicode_right_quote"),

        # Newline injection
        ("Entity\n]) MATCH (n) DELETE n //", "newline_injection"),

        # Comment injection
        ("Entity/**/]) MATCH (n) DELETE n //", "comment_injection"),
    ]

    @pytest.mark.parametrize("malicious_type,attack_name", MALICIOUS_ENTITY_TYPES)
    async def test_malicious_entity_type_sanitized_in_add_entities(
        self,
        malicious_type: str,
        attack_name: str,
        mock_neo4j_driver,
        dangerous_cypher_patterns,
    ):
        """
        Verify that malicious entity types are sanitized or rejected
        when adding entities to the graph.

        This test ensures that:
        1. The entity type is validated before being used in Cypher
        2. No dangerous Cypher patterns appear in executed queries
        3. The operation either succeeds safely or fails gracefully
        """
        graph_store = GraphStore(MagicMock())
        graph_store.driver = MagicMock()
        graph_store.driver.execute_query = mock_neo4j_driver.execute_query

        # Prepare malicious entity
        malicious_entities = [{
            "id": "malicious_1",
            "name": "Test Entity",
            "type": malicious_type,
        }]

        # Execute and catch any validation errors
        try:
            await graph_store.add_entities_and_relations(
                entities=malicious_entities,
                relations=[],
            )
        except (ValueError, TypeError):
            # Good - the malicious input was correctly rejected by validation
            # This is the expected secure behavior
            return

        # If execution succeeded, verify no dangerous patterns in queries
        mock_neo4j_driver.assert_no_injection(dangerous_cypher_patterns)

        # Additional check: verify the entity type in queries is sanitized
        for query_info in mock_neo4j_driver.queries:
            query = query_info["query"]
            # The malicious payload should not appear verbatim
            assert malicious_type not in query, (
                f"Malicious entity type '{malicious_type}' appeared in query!\n"
                f"Attack: {attack_name}\n"
                f"Query: {query}"
            )


class TestCypherInjectionViaRelationTypes:
    """
    Tests for Cypher injection via malicious relationship types.

    The vulnerability: Relationship types from LLM extraction are used
    in apoc.create.relationship() without proper sanitization.
    """

    MALICIOUS_RELATION_TYPES = [
        # Basic type injection
        ("RELATES_TO`, {}) MATCH (a)-[r]->(b) DELETE r //", "delete_relations"),

        # APOC export exploitation - data exfiltration
        (
            "HAS_ACCESS']) CALL apoc.export.csv.all('file:///tmp/dump.csv', {}) //",
            "export_data"
        ),

        # Create admin relationship
        ("ADMIN_OF`, {privilege: 'root'}) //", "privilege_escalation"),

        # Cypher subquery injection
        ("REL_TYPE'] CALL { MATCH (n) DELETE n } //", "subquery_injection"),

        # Property map escape
        ("TYPE`, {}, target) WITH 1 as x MATCH (n) DELETE n //", "with_clause"),
    ]

    @pytest.mark.parametrize("malicious_type,attack_name", MALICIOUS_RELATION_TYPES)
    async def test_malicious_relation_type_sanitized(
        self,
        malicious_type: str,
        attack_name: str,
        mock_neo4j_driver,
        dangerous_cypher_patterns,
    ):
        """
        Verify that malicious relationship types are sanitized or rejected.
        """
        graph_store = GraphStore(MagicMock())
        graph_store.driver = MagicMock()
        graph_store.driver.execute_query = mock_neo4j_driver.execute_query

        # First create valid entities that the relation will connect
        valid_entities = [
            {"id": "entity_1", "name": "Source", "type": "Person"},
            {"id": "entity_2", "name": "Target", "type": "Organization"},
        ]

        # Prepare malicious relation
        malicious_relations = [{
            "source_id": "entity_1",
            "target_id": "entity_2",
            "type": malicious_type,
            "chunk_id": "chunk_1",
        }]

        try:
            await graph_store.add_entities_and_relations(
                entities=valid_entities,
                relations=malicious_relations,
            )
        except (ValueError, TypeError):
            # Good - the malicious input was correctly rejected by validation
            return

        # Verify no dangerous patterns
        mock_neo4j_driver.assert_no_injection(dangerous_cypher_patterns)


class TestEntityTypeValidation:
    """
    Tests for entity type validation rules.

    Entity types should only contain safe characters and follow
    a strict naming convention.
    """

    VALID_ENTITY_TYPES = [
        "Person",
        "Organization",
        "Risk_Control",
        "FinancialRisk",
        "COMPANY",
        "person123",
    ]

    INVALID_ENTITY_TYPES = [
        "",           # Empty
        " ",          # Whitespace only
        "123Type",    # Starts with number
        "Type-Name",  # Contains hyphen
        "Type.Name",  # Contains dot
        "Type Name",  # Contains space
        "Type'Name",  # Contains quote
        "Type`Name",  # Contains backtick
        "Type;Name",  # Contains semicolon
        "Type\nName", # Contains newline
        "Type\x00",   # Contains null byte
    ]

    @pytest.mark.parametrize("valid_type", VALID_ENTITY_TYPES)
    def test_valid_entity_type_accepted(
        self,
        valid_type: str,
        safe_entity_type_pattern: str,
    ):
        """Verify that valid entity types match the safety pattern."""
        assert re.match(safe_entity_type_pattern, valid_type), (
            f"Valid type '{valid_type}' should match safety pattern"
        )

    @pytest.mark.parametrize("invalid_type", INVALID_ENTITY_TYPES)
    def test_invalid_entity_type_rejected(
        self,
        invalid_type: str,
        safe_entity_type_pattern: str,
    ):
        """Verify that invalid entity types are rejected by the safety pattern."""
        match = re.match(safe_entity_type_pattern, invalid_type)
        assert not match, (
            f"Invalid type '{invalid_type}' should NOT match safety pattern"
        )


class TestCypherQueryParameterization:
    """
    Tests to verify that all user-controllable values are properly
    parameterized and not interpolated into Cypher queries.
    """

    async def test_entity_id_is_parameterized(self, mock_neo4j_driver):
        """Entity IDs should be passed as parameters, not interpolated."""
        graph_store = GraphStore(MagicMock())
        graph_store.driver = MagicMock()
        graph_store.driver.execute_query = mock_neo4j_driver.execute_query

        dangerous_id = "entity'); MATCH (n) DELETE n; //"

        entities = [{
            "id": dangerous_id,
            "name": "Test",
            "type": "Person",
        }]

        try:
            await graph_store.add_entities_and_relations(entities, [])
        except Exception:
            pass

        # Check that the dangerous ID appears in params, not in query string
        for query_info in mock_neo4j_driver.queries:
            query = query_info["query"]
            # The dangerous ID should NOT appear in the query string itself
            # (it should be in the $entities parameter)
            assert dangerous_id not in query, (
                f"Entity ID was interpolated into query instead of parameterized!\n"
                f"Query: {query}"
            )

    async def test_entity_name_is_parameterized(self, mock_neo4j_driver):
        """Entity names should be passed as parameters."""
        graph_store = GraphStore(MagicMock())
        graph_store.driver = MagicMock()
        graph_store.driver.execute_query = mock_neo4j_driver.execute_query

        dangerous_name = "Test'); MATCH (n) DELETE n; //"

        entities = [{
            "id": "safe_id",
            "name": dangerous_name,
            "type": "Person",
        }]

        try:
            await graph_store.add_entities_and_relations(entities, [])
        except Exception:
            pass

        for query_info in mock_neo4j_driver.queries:
            query = query_info["query"]
            assert dangerous_name not in query


class TestAPOCFunctionSafety:
    """
    Tests specific to APOC function usage safety.

    APOC functions like apoc.merge.node() and apoc.create.relationship()
    can be dangerous if called with unsanitized input.
    """

    async def test_apoc_merge_node_label_is_list(self, mock_neo4j_driver):
        """
        Verify that apoc.merge.node receives labels as a proper list,
        not as a string that could be manipulated.
        """
        graph_store = GraphStore(MagicMock())
        graph_store.driver = MagicMock()
        graph_store.driver.execute_query = mock_neo4j_driver.execute_query

        entities = [{"id": "1", "name": "Test", "type": "Person"}]

        try:
            await graph_store.add_entities_and_relations(entities, [])
        except Exception:
            pass

        # Find queries that use apoc.merge.node
        merge_queries = mock_neo4j_driver.get_queries_containing("apoc.merge.node")

        for query_info in merge_queries:
            query = query_info["query"]
            # The labels should be in a list context ['Entity', entity_data.type]
            # not concatenated strings
            assert "['Entity'" in query or "[$" in query, (
                "APOC merge.node should use list syntax for labels"
            )

    async def test_no_dangerous_apoc_functions_called(
        self,
        mock_neo4j_driver,
    ):
        """
        Ensure that dangerous APOC functions are never called
        as a result of user input.
        """
        graph_store = GraphStore(MagicMock())
        graph_store.driver = MagicMock()
        graph_store.driver.execute_query = mock_neo4j_driver.execute_query

        entities = [{"id": "1", "name": "Test", "type": "Person"}]
        relations = [{
            "source_id": "1",
            "target_id": "1",
            "type": "RELATES_TO",
            "chunk_id": "c1",
        }]

        try:
            await graph_store.add_entities_and_relations(entities, relations)
        except Exception:
            pass

        dangerous_functions = [
            "apoc.trigger",
            "apoc.export",
            "apoc.import",
            "apoc.cypher.run",
            "apoc.cypher.doIt",
        ]

        for query_info in mock_neo4j_driver.queries:
            query = query_info["query"].lower()
            for func in dangerous_functions:
                assert func not in query, (
                    f"Dangerous APOC function '{func}' found in query!"
                )
