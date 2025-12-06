#!/usr/bin/env python3
"""
Tests for the entity resolver database initialization module.

Note: These tests are skipped because the system now uses PostgreSQL
instead of SQLite. The legacy SQLite entity_resolver.db_init module has been removed.
"""

import pytest


@pytest.mark.skip(reason="Legacy SQLite db_init module removed - system uses PostgreSQL")
class TestEntityResolverDbInit:
    """Test suite for entity resolver database initialization (skipped - using PostgreSQL)."""

    def test_placeholder(self):
        """Placeholder test - all SQLite database init tests are skipped."""
        pass
