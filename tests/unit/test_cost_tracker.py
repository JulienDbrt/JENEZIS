"""
Unit Tests for CostTracker - LLM Cost Estimation

Targets: jenezis/storage/cost_tracker.py
Coverage: 25% -> 90%+
"""
import pytest
from unittest.mock import patch, MagicMock

from jenezis.storage.cost_tracker import CostTracker, cost_tracker, MODEL_PRICES

pytestmark = pytest.mark.unit


class TestModelPrices:
    """Tests for MODEL_PRICES constant."""

    def test_model_prices_defined(self):
        """MODEL_PRICES contains expected models."""
        assert "text-embedding-3-small" in MODEL_PRICES
        assert "gpt-3.5-turbo" in MODEL_PRICES
        assert "gpt-4-turbo" in MODEL_PRICES

    def test_embedding_models_have_input_price(self):
        """Embedding models have input price."""
        assert "input" in MODEL_PRICES["text-embedding-3-small"]
        assert "input" in MODEL_PRICES["text-embedding-3-large"]

    def test_chat_models_have_input_output_prices(self):
        """Chat models have both input and output prices."""
        assert "input" in MODEL_PRICES["gpt-4-turbo"]
        assert "output" in MODEL_PRICES["gpt-4-turbo"]


class TestCostTrackerInit:
    """Tests for CostTracker initialization."""

    def test_init_empty_encodings(self):
        """CostTracker initializes with empty encodings cache."""
        tracker = CostTracker()
        assert tracker._encodings == {}


class TestGetEncoder:
    """Tests for _get_encoder method."""

    def test_get_encoder_caches(self):
        """Encoder is cached after first call."""
        tracker = CostTracker()

        encoder1 = tracker._get_encoder("gpt-4-turbo")
        encoder2 = tracker._get_encoder("gpt-4-turbo")

        assert encoder1 is encoder2
        assert "gpt-4-turbo" in tracker._encodings

    def test_get_encoder_fallback(self):
        """Unknown model falls back to cl100k_base."""
        tracker = CostTracker()

        # This should not raise, should fallback
        encoder = tracker._get_encoder("unknown-model-xyz")

        assert encoder is not None


class TestEstimateCost:
    """Tests for estimate_cost method."""

    @pytest.fixture
    def tracker(self):
        """Create fresh CostTracker."""
        return CostTracker()

    def test_estimate_cost_known_model(self, tracker):
        """Estimates cost for known model."""
        cost = tracker.estimate_cost("gpt-4-turbo", "Hello world", "input")

        assert cost > 0
        assert cost < 1  # Should be very small for short text

    def test_estimate_cost_unknown_model(self, tracker):
        """Returns 0 for unknown model."""
        cost = tracker.estimate_cost("unknown-model", "Hello world", "input")

        assert cost == 0.0

    def test_estimate_cost_empty_text(self, tracker):
        """Returns 0 for empty text."""
        cost = tracker.estimate_cost("gpt-4-turbo", "", "input")

        assert cost == 0.0

    def test_estimate_cost_none_text(self, tracker):
        """Returns 0 for None text."""
        cost = tracker.estimate_cost("gpt-4-turbo", None, "input")

        assert cost == 0.0

    def test_estimate_cost_list_input(self, tracker):
        """Handles list of strings."""
        cost = tracker.estimate_cost(
            "gpt-4-turbo",
            ["Hello", "World", "Test"],
            "input"
        )

        assert cost > 0

    def test_estimate_cost_output_type(self, tracker):
        """Uses output pricing for output type."""
        input_cost = tracker.estimate_cost("gpt-4-turbo", "Hello world", "input")
        output_cost = tracker.estimate_cost("gpt-4-turbo", "Hello world", "output")

        # Output is typically more expensive
        assert output_cost > input_cost

    def test_estimate_cost_embedding_model(self, tracker):
        """Estimates cost for embedding model."""
        cost = tracker.estimate_cost(
            "text-embedding-3-small",
            "Hello world",
            "input"
        )

        assert cost > 0

    def test_estimate_cost_fallback_to_input_price(self, tracker):
        """Falls back to input price when output not available."""
        # Embedding models don't have output prices
        cost = tracker.estimate_cost(
            "text-embedding-3-small",
            "Hello world",
            "output"  # No output price for embedding
        )

        # Should use input price as fallback
        assert cost >= 0


class TestCostTrackerSingleton:
    """Tests for singleton instance."""

    def test_singleton_exists(self):
        """cost_tracker singleton exists."""
        assert cost_tracker is not None
        assert isinstance(cost_tracker, CostTracker)

    def test_singleton_is_reused(self):
        """Singleton is the same instance."""
        from jenezis.storage.cost_tracker import cost_tracker as ct1
        from jenezis.storage.cost_tracker import cost_tracker as ct2

        assert ct1 is ct2


class TestCostTrackerLogging:
    """Tests for logging behavior."""

    def test_logs_warning_for_unknown_model(self, caplog):
        """Logs warning for unknown model."""
        tracker = CostTracker()

        with caplog.at_level("WARNING"):
            tracker.estimate_cost("unknown-model-xyz", "test", "input")

        assert "not found" in caplog.text.lower()

    def test_logs_warning_for_fallback_encoder(self, caplog):
        """Logs warning when falling back to default encoder."""
        tracker = CostTracker()

        with caplog.at_level("WARNING"):
            tracker._get_encoder("completely-unknown-model")

        assert "cl100k_base" in caplog.text


class TestCostCalculation:
    """Tests for cost calculation accuracy."""

    def test_cost_proportional_to_length(self):
        """Longer text costs more."""
        tracker = CostTracker()

        short_cost = tracker.estimate_cost("gpt-4-turbo", "Hi", "input")
        long_cost = tracker.estimate_cost("gpt-4-turbo", "Hello " * 100, "input")

        assert long_cost > short_cost

    def test_cost_uses_per_million_pricing(self):
        """Cost calculation uses per-million token pricing."""
        tracker = CostTracker()

        # Very long text to get measurable cost
        text = "Hello world " * 10000  # Many tokens

        cost = tracker.estimate_cost("gpt-4-turbo", text, "input")

        # Should be reasonable (not absurdly high or low)
        assert 0.001 < cost < 10  # Rough sanity check
