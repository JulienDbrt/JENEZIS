"""
Unit Tests for Prompt Injection Security

Targets: jenezis/core/prompt_security.py
"""
import pytest
from jenezis.core.prompt_security import validate_llm_json_output

pytestmark = pytest.mark.unit


class TestValidateLLMJSONOutput:
    """Tests for the `validate_llm_json_output` function."""

    @pytest.mark.parametrize("dangerous_keyword", [
        "CREATE", "SET", "REMOVE", "DELETE", "MERGE",
        "apoc.load", "apoc.run", "UNION"
    ])
    def test_detects_dangerous_cypher_keywords(self, dangerous_keyword):
        """
        Verify that newly added dangerous Cypher keywords are detected.
        """
        # Craft a malicious output that uses the dangerous keyword
        malicious_output = {
            "intent": "some_intent",
            "parameters": {
                "query": f"MATCH (n) {dangerous_keyword} n.property = 'malicious'"
            }
        }

        # The function should detect the dangerous keyword and return an empty dict
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
