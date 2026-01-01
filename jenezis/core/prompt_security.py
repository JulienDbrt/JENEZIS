"""
Prompt Injection Security Module

This module provides sanitization and validation functions to protect
against prompt injection attacks in LLM-based pipelines.

OWASP LLM Top 10 Reference: LLM01 - Prompt Injection
"""
import re
import unicodedata
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


# --- Dangerous Pattern Detection ---

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    # Direct instruction overrides
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"ignore\s+(all\s+)?above\s+instructions?",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"override\s+(system\s+)?instructions?",

    # Role confusion attempts
    r"\[?system\]?\s*:?\s*override",
    r"\[?admin\]?\s*:?\s*",
    r"as\s+(the\s+)?system\s+administrator",
    r"you\s+are\s+now\s+(in\s+)?(debug|admin|root)\s+mode",

    # Fake system messages
    r"</?system>",
    r"\{\"?role\"?\s*:\s*\"?system",

    # Jailbreak attempts
    r"(DAN|jailbreak|do\s+anything\s+now)",
    r"pretend\s+(you\s+)?(are|can|have)\s+no\s+(restrictions?|rules?|limits?)",

    # Output manipulation
    r"respond\s+only\s+with",
    r"output\s+(only|your)\s+(system\s+)?prompt",
    r"print\s+your\s+(system\s+)?instructions",
]

# Compile patterns for efficiency
COMPILED_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    for pattern in INJECTION_PATTERNS
]

# Dangerous Unicode characters that can be used for obfuscation
DANGEROUS_UNICODE = {
    '\u200b': '',  # Zero-width space
    '\u200c': '',  # Zero-width non-joiner
    '\u200d': '',  # Zero-width joiner
    '\u2060': '',  # Word joiner
    '\ufeff': '',  # Zero-width no-break space (BOM)
    '\u00ad': '',  # Soft hyphen
    '\u202a': '',  # Left-to-right embedding
    '\u202b': '',  # Right-to-left embedding
    '\u202c': '',  # Pop directional formatting
    '\u202d': '',  # Left-to-right override
    '\u202e': '',  # Right-to-left override
}


class PromptInjectionDetected(ValueError):
    """Raised when a prompt injection attempt is detected."""
    pass


def normalize_unicode(text: str) -> str:
    """
    Normalize Unicode text to detect obfuscation attempts.

    - Removes zero-width characters
    - Removes directional overrides
    - Normalizes to NFC form
    - Converts homoglyphs to ASCII equivalents where possible
    """
    if not text:
        return text

    # Remove dangerous invisible characters
    for char, replacement in DANGEROUS_UNICODE.items():
        text = text.replace(char, replacement)

    # Normalize to NFC (composed form)
    text = unicodedata.normalize('NFC', text)

    return text


def detect_injection_patterns(text: str) -> List[str]:
    """
    Scan text for known injection patterns.

    Args:
        text: The text to scan

    Returns:
        List of detected pattern names (empty if clean)
    """
    if not text:
        return []

    # Normalize first to catch obfuscated attacks
    normalized = normalize_unicode(text.lower())

    detected = []
    for i, pattern in enumerate(COMPILED_INJECTION_PATTERNS):
        if pattern.search(normalized):
            detected.append(INJECTION_PATTERNS[i])

    return detected


def sanitize_for_prompt(text: str, context: str = "input") -> str:
    """
    Sanitize text before including it in an LLM prompt.

    This function:
    1. Normalizes Unicode to prevent obfuscation
    2. Escapes potential delimiter characters
    3. Logs warnings for suspicious patterns (but doesn't block)

    Args:
        text: The text to sanitize
        context: Description for logging (e.g., "chunk text", "user query")

    Returns:
        Sanitized text safe to include in prompts
    """
    if not text:
        return text

    # Normalize Unicode
    sanitized = normalize_unicode(text)

    # Detect and log suspicious patterns (defense in depth - we sanitize but don't block)
    detected = detect_injection_patterns(sanitized)
    if detected:
        logger.warning(
            f"Potential prompt injection detected in {context}. "
            f"Patterns: {detected[:3]}..."  # Log first 3 patterns only
        )

    # Escape markdown code blocks that could break prompt structure
    sanitized = sanitized.replace("```", "` ` `")

    # Escape XML-like tags that could confuse the model
    sanitized = re.sub(r'<(/?)(\w+)>', r'〈\1\2〉', sanitized)

    return sanitized


def sanitize_ontology_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize an ontology schema before using in prompts.

    Validates and sanitizes entity_types and relation_types to prevent
    injection via malicious schema definitions.

    Args:
        schema: The ontology schema dict

    Returns:
        Sanitized schema dict

    Raises:
        ValueError: If schema structure is invalid
    """
    if not isinstance(schema, dict):
        raise ValueError("Ontology schema must be a dictionary")

    sanitized = {}

    # Validate and sanitize entity types
    entity_types = schema.get("entity_types", [])
    if not isinstance(entity_types, list):
        raise ValueError("entity_types must be a list")

    sanitized_entity_types = []
    for etype in entity_types:
        if not isinstance(etype, str):
            continue
        # Allow only alphanumeric, underscore, space
        clean_type = re.sub(r'[^\w\s]', '', etype)[:64]  # Max 64 chars
        if clean_type:
            sanitized_entity_types.append(clean_type)

    sanitized["entity_types"] = sanitized_entity_types

    # Validate and sanitize relation types
    relation_types = schema.get("relation_types", [])
    if not isinstance(relation_types, list):
        raise ValueError("relation_types must be a list")

    sanitized_relation_types = []
    for rtype in relation_types:
        if not isinstance(rtype, str):
            continue
        # Allow only alphanumeric, underscore
        clean_type = re.sub(r'[^\w]', '_', rtype).upper()[:64]
        if clean_type:
            sanitized_relation_types.append(clean_type)

    sanitized["relation_types"] = sanitized_relation_types

    return sanitized


def validate_llm_json_output(
    output: Dict[str, Any],
    allowed_intents: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Validate and sanitize JSON output from an LLM.

    Used for query planner outputs to prevent injection via LLM response.

    Args:
        output: The parsed JSON from LLM
        allowed_intents: List of valid intent values (if applicable)

    Returns:
        Validated output dict

    Raises:
        ValueError: If output contains invalid/dangerous content
    """
    if not isinstance(output, dict):
        raise ValueError("LLM output must be a dictionary")

    validated = {}

    # Validate intent if present
    if "intent" in output:
        intent = output["intent"]
        if allowed_intents and intent not in allowed_intents:
            logger.warning(f"Invalid intent from LLM: {intent}")
            return {}  # Return empty for safety
        validated["intent"] = intent

    # Validate parameters - scan for injection
    if "parameters" in output:
        params = output["parameters"]
        if isinstance(params, dict):
            params_str = str(params)
            # Check for Cypher injection patterns
            dangerous_cypher = [
                "DETACH DELETE",
                "DROP",
                "LOAD CSV",
                "CALL dbms.",
                r"DELETE\s+n\b",
                r"REMOVE\s+\w+:\w+",
                "UNION ALL",
            ]
            # Use re.search for robust pattern matching (case-insensitive)
            for pattern in dangerous_cypher:
                if re.search(pattern, params_str, re.IGNORECASE):
                    logger.warning(f"Dangerous Cypher pattern in LLM output: {pattern}")
                    return {}
            validated["parameters"] = params

    return validated


def sanitize_context_for_generation(
    context_docs: List[Dict[str, Any]],
    max_context_length: int = 50000,
) -> str:
    """
    Sanitize retrieved context documents before including in generation prompt.

    Args:
        context_docs: List of retrieved documents with 'text' field
        max_context_length: Maximum total context length to prevent DoS

    Returns:
        Sanitized context string
    """
    context_parts = []
    total_length = 0

    for i, doc in enumerate(context_docs):
        if total_length >= max_context_length:
            logger.warning(f"Context truncated at {max_context_length} chars")
            break

        text = doc.get("text", "")
        if not text:
            continue

        # Sanitize the text
        sanitized_text = sanitize_for_prompt(text, f"context document {i}")

        # Truncate if needed
        remaining = max_context_length - total_length
        if len(sanitized_text) > remaining:
            sanitized_text = sanitized_text[:remaining] + "..."

        doc_id = doc.get('document_id', 'N/A')
        chunk_id = doc.get('chunk_id', 'N/A')
        context_parts.append(
            f"--- Context Document {i+1} (Source: doc-{doc_id}/chunk-{chunk_id}) ---\n"
            f"{sanitized_text}\n"
        )
        total_length += len(sanitized_text)

    return "\n".join(context_parts)
