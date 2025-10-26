#!/usr/bin/env python3
"""
Tests pour les fonctions refactorisées d'analyze_unmapped.py.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Add src to path for imports
sys.path.insert(0, "/Users/juliendabert/Desktop/Erwin-Harmonizer/src")


class TestAnalyzeUnmappedRefactored:
    """Test suite pour les fonctions refactorisées d'analyze_unmapped."""

    @pytest.mark.unit
    def test_load_mapped_skills(self):
        """Test load_mapped_skills function."""
        from src.cli.analyze_unmapped import load_mapped_skills

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        # Create test database
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE skills (id INTEGER, canonical_name TEXT)")
        cursor.execute("INSERT INTO skills VALUES (1, 'python')")
        cursor.execute("INSERT INTO skills VALUES (2, 'javascript')")
        cursor.execute("INSERT INTO skills VALUES (3, 'java')")
        conn.commit()
        conn.close()

        # Test function
        mapped_skills = load_mapped_skills(temp_db_path)

        assert mapped_skills == {"python", "javascript", "java"}
        assert len(mapped_skills) == 3

        # Cleanup
        Path(temp_db_path).unlink()

    @pytest.mark.unit
    def test_load_skills_data(self):
        """Test load_skills_data function."""
        from src.cli.analyze_unmapped import load_skills_data

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as temp_csv:
            temp_csv.write("competence\npython\njavascript\nunknown_skill\n")
            temp_csv_path = temp_csv.name

        # Test function
        df = load_skills_data(temp_csv_path)

        assert isinstance(df, pd.DataFrame)
        assert "competence" in df.columns
        assert len(df) == 3
        assert "python" in df["competence"].values

        # Cleanup
        Path(temp_csv_path).unlink()

    @pytest.mark.unit
    def test_identify_unmapped_skills(self):
        """Test identify_unmapped_skills function."""
        from src.cli.analyze_unmapped import identify_unmapped_skills

        df = pd.DataFrame(
            {"competence": ["python", "javascript", "unknown1", "unknown2", "python"]}
        )
        mapped_skills = {"python", "javascript"}

        unmapped = identify_unmapped_skills(df, mapped_skills)

        assert unmapped == {"unknown1", "unknown2"}
        assert "python" not in unmapped
        assert "javascript" not in unmapped

    @pytest.mark.unit
    def test_count_skill_frequencies(self):
        """Test count_skill_frequencies function."""
        from src.cli.analyze_unmapped import count_skill_frequencies

        df = pd.DataFrame(
            {"competence": ["unknown1", "unknown1", "unknown1", "unknown2", "unknown2", "python"]}
        )
        unmapped_skills = {"unknown1", "unknown2"}

        frequencies = count_skill_frequencies(df, unmapped_skills)

        assert frequencies["unknown1"] == 3
        assert frequencies["unknown2"] == 2
        assert "python" not in frequencies

    @pytest.mark.unit
    def test_sort_skills_by_frequency(self):
        """Test sort_skills_by_frequency function."""
        from src.cli.analyze_unmapped import sort_skills_by_frequency

        unmapped_counts = {"rare": 1, "common": 5, "medium": 3}

        sorted_skills = sort_skills_by_frequency(unmapped_counts)

        assert sorted_skills == [("common", 5), ("medium", 3), ("rare", 1)]
        assert sorted_skills[0][0] == "common"
        assert sorted_skills[0][1] == 5

    @pytest.mark.unit
    def test_detect_frameworks(self):
        """Test detect_frameworks function."""
        from src.cli.analyze_unmapped import detect_frameworks

        unmapped_skills = {
            "react.js",
            "angular.js",
            "express framework",
            "lodash lib",
            "python",
            "normal skill",
        }

        frameworks = detect_frameworks(unmapped_skills)

        assert "react.js" in frameworks
        assert "angular.js" in frameworks
        assert "express framework" in frameworks
        assert "lodash lib" in frameworks
        assert "python" not in frameworks
        assert "normal skill" not in frameworks

    @pytest.mark.unit
    def test_detect_tools(self):
        """Test detect_tools function."""
        from src.cli.analyze_unmapped import detect_tools

        unmapped_skills = {
            "SQL Server",
            "Project Manager",
            "Management Suite",
            "Database Tool",
            "python",
            "normal skill",
        }

        tools = detect_tools(unmapped_skills)

        assert "SQL Server" in tools
        assert "Project Manager" in tools
        assert "Management Suite" in tools
        assert "Database Tool" in tools
        assert "python" not in tools
        assert "normal skill" not in tools

    @pytest.mark.unit
    def test_detect_certifications(self):
        """Test detect_certifications function."""
        from src.cli.analyze_unmapped import detect_certifications

        unmapped_skills = {
            "AWS Certified",
            "Microsoft Certification",
            "Google CRT",
            "python",
            "normal skill",
        }

        certifications = detect_certifications(unmapped_skills)

        assert "AWS Certified" in certifications
        assert "Microsoft Certification" in certifications
        assert "Google CRT" in certifications
        assert "python" not in certifications
        assert "normal skill" not in certifications

    @pytest.mark.unit
    def test_calculate_statistics(self):
        """Test calculate_statistics function."""
        from src.cli.analyze_unmapped import calculate_statistics

        df = pd.DataFrame(
            {"competence": ["unknown1", "unknown1", "unknown2", "python", "javascript"]}
        )
        unmapped_skills = {"unknown1", "unknown2"}
        unmapped_counts = {"unknown1": 2, "unknown2": 1}

        stats = calculate_statistics(df, unmapped_skills, unmapped_counts)

        assert stats["total_unmapped_skills"] == 2
        assert stats["total_skills"] == 4  # unique skills: unknown1, unknown2, python, javascript
        assert stats["total_unmapped_occurrences"] == 3
        assert stats["total_relations"] == 5
        assert stats["unmapped_percentage"] == 60.0  # 3/5 * 100

    @pytest.mark.unit
    def test_save_analysis_results(self):
        """Test save_analysis_results function."""
        from src.cli.analyze_unmapped import save_analysis_results

        sorted_unmapped = [("skill1", 100), ("skill2", 50)]

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        save_analysis_results(sorted_unmapped, temp_path)

        # Verify file was created and has correct content
        assert temp_path.exists()
        df_saved = pd.read_csv(temp_path)
        assert len(df_saved) == 2
        assert list(df_saved.columns) == ["skill", "count"]
        assert df_saved.iloc[0]["skill"] == "skill1"
        assert df_saved.iloc[0]["count"] == 100

        # Cleanup
        temp_path.unlink()

    @pytest.mark.unit
    @patch("builtins.print")
    def test_print_analysis_results(self, mock_print):
        """Test print_analysis_results function."""
        from src.cli.analyze_unmapped import print_analysis_results

        stats = {
            "total_unmapped_skills": 100,
            "total_skills": 200,
            "total_unmapped_occurrences": 500,
            "total_relations": 1000,
            "unmapped_percentage": 50.0,
        }
        sorted_unmapped = [("skill1", 100), ("skill2", 50)]
        frameworks = ["react.js", "angular.js"]
        tools = ["SQL Server"]
        certifications = ["AWS Certified"]

        print_analysis_results(stats, sorted_unmapped, frameworks, tools, certifications)

        # Verify that print was called
        assert mock_print.call_count > 0
        # Check some key outputs were printed
        calls = [str(call) for call in mock_print.call_args_list]
        assert any("ANALYSE DES COMPÉTENCES" in call for call in calls)
        assert any("PATTERNS DÉTECTÉS" in call for call in calls)

    @pytest.mark.unit
    def test_analyze_unmapped_skills_integration(self):
        """Test analyze_unmapped_skills integration function."""
        from src.cli.analyze_unmapped import analyze_unmapped_skills

        # Create test CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as temp_csv:
            temp_csv.write("competence\npython\njavascript\nunknown.js\nunknown_tool\npython\n")
            temp_csv_path = temp_csv.name

        # Create test database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE skills (id INTEGER, canonical_name TEXT)")
        cursor.execute("INSERT INTO skills VALUES (1, 'python')")
        cursor.execute("INSERT INTO skills VALUES (2, 'javascript')")
        conn.commit()
        conn.close()

        # Create temp output directory
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            # Test the main function
            results = analyze_unmapped_skills(temp_csv_path, temp_db_path, output_dir)

            # Verify results structure
            assert "stats" in results
            assert "sorted_unmapped" in results
            assert "patterns" in results
            assert "output_file" in results

            # Verify stats
            stats = results["stats"]
            assert stats["total_unmapped_skills"] == 2  # unknown.js, unknown_tool
            assert stats["total_skills"] == 4  # python, javascript, unknown.js, unknown_tool

            # Verify patterns
            patterns = results["patterns"]
            assert "unknown.js" in patterns["frameworks"]  # Contains .js
            assert "unknown_tool" in patterns["tools"]  # Contains tool

            # Verify output file was created
            assert Path(results["output_file"]).exists()

        # Cleanup
        Path(temp_csv_path).unlink()
        Path(temp_db_path).unlink()

    @pytest.mark.unit
    @patch("src.cli.analyze_unmapped.analyze_unmapped_skills")
    @patch("src.cli.analyze_unmapped.print_analysis_results")
    def test_main_function(self, mock_print_results, mock_analyze):
        """Test main function."""
        from src.cli.analyze_unmapped import main

        # Mock return value
        mock_results = {
            "stats": {"total_unmapped_skills": 10},
            "sorted_unmapped": [("skill1", 100)],
            "patterns": {
                "frameworks": ["react.js"],
                "tools": ["SQL Server"],
                "certifications": ["AWS Certified"],
            },
            "output_file": "/path/to/output.csv",
        }
        mock_analyze.return_value = mock_results

        # Call main
        with patch("builtins.print") as mock_print:
            main()

        # Verify functions were called
        mock_analyze.assert_called_once_with()
        mock_print_results.assert_called_once()
        mock_print.assert_called_with("\n✓ Analyse complète sauvegardée dans: /path/to/output.csv")

    @pytest.mark.unit
    def test_empty_data_handling(self):
        """Test handling of empty data."""
        from src.cli.analyze_unmapped import (
            count_skill_frequencies,
            detect_frameworks,
            identify_unmapped_skills,
        )

        # Empty DataFrame
        empty_df = pd.DataFrame({"competence": []})
        mapped_skills = {"python"}

        unmapped = identify_unmapped_skills(empty_df, mapped_skills)
        assert len(unmapped) == 0

        frequencies = count_skill_frequencies(empty_df, set())
        assert len(frequencies) == 0

        frameworks = detect_frameworks(set())
        assert len(frameworks) == 0

    @pytest.mark.unit
    def test_pattern_detection_case_insensitive(self):
        """Test that pattern detection is case insensitive."""
        from src.cli.analyze_unmapped import detect_certifications, detect_frameworks, detect_tools

        unmapped_skills = {
            "React.JS",
            "ANGULAR FRAMEWORK",
            "mysql SERVER",
            "AWS CERTIFIED",
            "Microsoft CERTIFICATION",
        }

        frameworks = detect_frameworks(unmapped_skills)
        tools = detect_tools(unmapped_skills)
        certifications = detect_certifications(unmapped_skills)

        assert "React.JS" in frameworks
        assert "ANGULAR FRAMEWORK" in frameworks
        assert "mysql SERVER" in tools
        assert "AWS CERTIFIED" in certifications
        assert "Microsoft CERTIFICATION" in certifications
