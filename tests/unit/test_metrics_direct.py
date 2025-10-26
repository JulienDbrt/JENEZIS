#!/usr/bin/env python3
"""
Direct tests for the metrics module functions.
"""

import time
from unittest.mock import patch

import pytest
from fastapi import Response


class TestMetricsFunctions:
    """Test the actual metrics module functions."""

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_track_request_metrics(self):
        """Test track_request_metrics function."""
        with patch("src.api.metrics.api_requests") as mock_counter:
            from src.api.metrics import track_request_metrics

            # Just call the function to ensure coverage
            track_request_metrics("GET", "/test", 200, 0.1)
            track_request_metrics("POST", "/test", 201, 0.2)

            # Check that metrics were called
            assert mock_counter.labels.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_track_cache_metrics(self):
        """Test track_cache_metrics function."""
        with patch("src.api.metrics.cache_size") as mock_gauge:
            from src.api.metrics import track_cache_metrics

            track_cache_metrics("aliases", 100)
            track_cache_metrics("skills", 50)

            assert mock_gauge.labels.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_track_harmonization(self):
        """Test track_harmonization function."""
        with patch("src.api.metrics.harmonization_results") as mock_counter:
            from src.api.metrics import track_harmonization

            track_harmonization("known", 5)
            track_harmonization("unknown", 2)

            assert mock_counter.labels.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_track_entity_resolution(self):
        """Test track_entity_resolution function."""
        with patch("src.api.metrics.entity_resolutions") as mock_counter:
            from src.api.metrics import track_entity_resolution

            track_entity_resolution("COMPANY", "known", 3)
            track_entity_resolution("SCHOOL", "unknown", 1)

            assert mock_counter.labels.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_track_database_query(self):
        """Test track_database_query function."""
        with patch("src.api.metrics.database_queries") as mock_histogram:
            from src.api.metrics import track_database_query

            track_database_query("SELECT", 0.01)
            track_database_query("INSERT", 0.05)

            assert mock_histogram.labels.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_track_error(self):
        """Test track_error function."""
        with patch("src.api.metrics.errors") as mock_counter:
            from src.api.metrics import track_error

            track_error("database_error", "/harmonize")
            track_error("auth_error", "/admin/reload")

            assert mock_counter.labels.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_metrics_endpoint(self):
        """Test metrics_endpoint function."""
        with patch("prometheus_client.generate_latest") as mock_generate:
            mock_generate.return_value = b"# HELP test\n# TYPE test counter\ntest 1.0\n"
            from src.api.metrics import metrics_endpoint

            response = metrics_endpoint()

            assert isinstance(response, Response)
            assert response.media_type == "text/plain"
            assert response.body == b"# HELP test\n# TYPE test counter\ntest 1.0\n"

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_time_database_query_decorator(self):
        """Test time_database_query decorator."""
        with patch("src.api.metrics.track_database_query") as mock_track:
            from src.api.metrics import time_database_query

            @time_database_query("test_query")
            def mock_function(value):
                time.sleep(0.01)  # Small delay to ensure measurable duration
                return value * 2

            result = mock_function(5)
            assert result == 10
            assert mock_track.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_time_database_query_decorator_with_exception(self):
        """Test time_database_query decorator with exception."""
        with patch("src.api.metrics.track_database_query") as mock_track:
            from src.api.metrics import time_database_query

            @time_database_query("error_query")
            def failing_function():
                raise ValueError("Test error")

            with pytest.raises(ValueError, match="Test error"):
                failing_function()

            # Decorator should still track the query despite exception
            assert mock_track.called

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""
        with patch("src.api.metrics.track_database_query"):
            from src.api.metrics import time_database_query

            @time_database_query("metadata_test")
            def documented_function():
                """This is a documented function."""
                return "result"

            assert documented_function.__name__ == "documented_function"
            assert documented_function.__doc__ == "This is a documented function."

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_decorator_with_multiple_arguments(self):
        """Test decorator with function having multiple arguments."""
        with patch("src.api.metrics.track_database_query"):
            from src.api.metrics import time_database_query

            @time_database_query("multi_arg_test")
            def multi_arg_function(a, b, c=10):
                return a + b + c

            result = multi_arg_function(1, 2, c=3)
            assert result == 6

    @pytest.mark.unit
    @pytest.mark.skip(reason="Prometheus registry conflicts")
    def test_decorator_with_kwargs(self):
        """Test decorator with keyword arguments."""
        with patch("src.api.metrics.track_database_query"):
            from src.api.metrics import time_database_query

            @time_database_query("kwargs_test")
            def kwargs_function(**kwargs):
                return sum(kwargs.values())

            result = kwargs_function(a=1, b=2, c=3)
            assert result == 6
