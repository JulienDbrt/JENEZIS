"""
Unit Tests for Prompt Injection Security

Targets: jenezis/core/prompt_security.py
"""
import pytest
from jenezis.core.prompt_security import validate_llm_json_output

pytestmark = pytest.mark.unit


class TestValidateLLMJSONOutput:
    """Tests for the `validate_llm_json_output` function."""

    @pytest.mark.parametrize("dangerous_pattern, query", [
        ("DETACH DELETE", "MATCH (n) DETACH DELETE n"),
        ("DROP", "DROP CONSTRAINT my_constraint"),
        ("LOAD CSV", "LOAD CSV FROM 'http://example.com/data.csv' AS row"),
        ("CALL dbms.", "CALL dbms.procedures()"),
        (r"DELETE\s+n\b", "MATCH (n) DELETE n"),
        (r"REMOVE\s+\w+:\w+", "MATCH (n) REMOVE n:Label"),
        ("UNION ALL", "MATCH (n) RETURN n.name UNION ALL MATCH (m) RETURN m.name"),
    ])
    def test_detects_dangerous_cypher_keywords(self, dangerous_pattern, query):
        """
        Verify that dangerous Cypher patterns are detected.
        """
        malicious_output = {
            "intent": "some_intent",
            "parameters": {
                "query": query
            }
        }

        validated_output = validate_llm_json_output(malicious_output)
        assert validated_output == {}

    def test_allows_safe_cypher_keywords(self):
        """
        Verify that safe Cypher keywords are not blocked.
        """
        safe_output = {
            "intent": "some_intent",
            "parameters": {
                "query": "MATCH (n) WHERE n.name = 'safe' RETURN n"
            }
        }

        validated_output = validate_llm_json_output(safe_output)
        assert validated_output == safe_output
