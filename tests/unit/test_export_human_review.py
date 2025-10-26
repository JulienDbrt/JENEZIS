#!/usr/bin/env python3
"""
Tests for export_human_review.py CLI tool.
"""

from unittest.mock import patch

import pandas as pd
import pytest


class TestExportHumanReview:
    """Test export_human_review functionality."""

    @pytest.mark.unit
    def test_parse_suggestion(self):
        """Test parsing suggestion string to components."""
        from src.cli.export_human_review import parse_suggestion

        # Test valid suggestion
        suggestion_str = str(
            {
                "canonical_name": "python",
                "aliases": ["py", "python3"],
                "parents": ["programming_languages"],
            }
        )

        canonical, aliases, parents = parse_suggestion(suggestion_str)

        assert canonical == "python"
        assert "py" in aliases
        assert "programming_languages" in parents

        # Test invalid suggestion
        invalid_str = "not a valid dict"
        canonical, aliases, parents = parse_suggestion(invalid_str)

        assert canonical == ""
        assert aliases == ""
        assert parents == ""

    @pytest.mark.unit
    def test_export_human_review_no_file(self, capsys):
        """Test export when needs review file doesn't exist."""
        from src.cli.export_human_review import export_human_review

        with patch("pathlib.Path.exists", return_value=False):
            result = export_human_review()

        assert result is False
        captured = capsys.readouterr()
        assert "Pas de fichier" in captured.out

    @pytest.mark.unit
    def test_export_human_review_empty_file(self, capsys):
        """Test export when file exists but is empty."""
        from src.cli.export_human_review import export_human_review

        empty_df = pd.DataFrame()

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pandas.read_csv", return_value=empty_df),
        ):
            result = export_human_review()

        assert result is True
        captured = capsys.readouterr()
        assert "Aucune compétence" in captured.out

    @pytest.mark.unit
    def test_export_human_review_success(self, capsys):
        """Test successful export with data."""
        from src.cli.export_human_review import export_human_review

        sample_df = pd.DataFrame(
            {
                "skill": ["python", "javascript"],
                "count": [100, 50],
                "suggestion": [
                    str(
                        {"canonical_name": "python", "aliases": ["py"], "parents": ["programming"]}
                    ),
                    str(
                        {
                            "canonical_name": "javascript",
                            "aliases": ["js"],
                            "parents": ["programming"],
                        }
                    ),
                ],
            }
        )

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pandas.read_csv", return_value=sample_df),
            patch("pandas.DataFrame.to_csv"),
            patch("src.cli.export_human_review.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "2024-01-15_10-30-00"
            result = export_human_review()

        assert result is True
        captured = capsys.readouterr()
        assert "2 compétences à valider" in captured.out
        assert "python" in captured.out

    @pytest.mark.unit
    def test_main_success(self):
        """Test main function with successful execution."""
        from src.cli.export_human_review import main

        with (
            patch("src.cli.export_human_review.export_human_review", return_value=True),
            patch("sys.exit") as mock_exit,
        ):
            main()
            mock_exit.assert_called_with(0)

    @pytest.mark.unit
    def test_main_failure(self):
        """Test main function with failed export."""
        from src.cli.export_human_review import main

        with (
            patch("src.cli.export_human_review.export_human_review", return_value=False),
            patch("sys.exit") as mock_exit,
        ):
            main()
            mock_exit.assert_called_with(1)

    @pytest.mark.unit
    def test_output_file_generation(self):
        """Test output file names are generated correctly."""
        from src.cli.export_human_review import export_human_review

        sample_df = pd.DataFrame(
            {
                "skill": ["test"],
                "count": [1],
                "suggestion": [str({"canonical_name": "test", "aliases": [], "parents": []})],
            }
        )

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pandas.read_csv", return_value=sample_df),
            patch("pandas.DataFrame.to_csv") as mock_to_csv,
        ):
            export_human_review()

        # Should save twice: timestamped and latest
        assert mock_to_csv.call_count == 2
