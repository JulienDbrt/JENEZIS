"""Integration test specific fixtures."""
import pytest


# Integration tests require running services
pytestmark = pytest.mark.integration
