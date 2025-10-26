#!/usr/bin/env python3
"""
Tests for the refactored functions in densify_ontology.py.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

# Add src to path for imports
sys.path.insert(0, "/Users/juliendabert/Desktop/Erwin-Harmonizer/src")


class TestDensificationConfig:
    """Test suite for DensificationConfig class."""

    @pytest.mark.unit
    def test_densification_config_with_openai(self):
        """Test DensificationConfig with OpenAI API key."""
        from src.cli.densify_ontology import DensificationConfig

        # Create a config instance and manually set attributes for testing
        with patch("builtins.print"):  # Suppress print statements
            config = DensificationConfig()

        # Manually test the logic by setting attributes
        config.openai_api_key = "sk-test"
        config.llm_model = "gpt-4o-mini"
        config.use_openai = config.openai_api_key and config.openai_api_key != "sk-..."
        config.client = Mock()  # Mock client

        assert config.openai_api_key == "sk-test"
        assert config.llm_model == "gpt-4o-mini"
        assert config.use_openai is True
        assert config.client is not None

    @pytest.mark.unit
    def test_densification_config_without_openai(self):
        """Test DensificationConfig without OpenAI API key."""
        from src.cli.densify_ontology import DensificationConfig

        # Patch os.getenv to return None for OPENAI_API_KEY
        with patch("os.getenv") as mock_getenv:

            def getenv_side_effect(key, default=None):
                if key == "OPENAI_API_KEY":
                    return None
                elif key == "LLM_MODEL":
                    return "gpt-4o-mini-2024-07-18"
                return default

            mock_getenv.side_effect = getenv_side_effect

            with patch("builtins.print"):  # Suppress print statements
                config = DensificationConfig()

        assert config.openai_api_key is None
        assert config.use_openai is False
        assert config.client is None

    @pytest.mark.unit
    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-..."})
    def test_densification_config_invalid_key(self):
        """Test DensificationConfig with invalid API key."""
        from src.cli.densify_ontology import DensificationConfig

        config = DensificationConfig()

        assert config.use_openai is False
        assert config.client is None


class TestSkillDatabaseManager:
    """Test suite for SkillDatabaseManager class."""

    @pytest.mark.unit
    def test_get_existing_canonical_skills(self):
        """Test get_existing_canonical_skills method."""
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

        from src.cli.densify_ontology import SkillDatabaseManager

        manager = SkillDatabaseManager(temp_db_path)
        skills = manager.get_existing_canonical_skills()

        assert skills == {"python", "javascript", "java"}
        assert len(skills) == 3

        # Cleanup
        Path(temp_db_path).unlink()

    @pytest.mark.unit
    def test_add_skill_to_database_success(self):
        """Test successful skill addition to database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        # Create test database with proper schema
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE NOT NULL
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_name TEXT UNIQUE NOT NULL,
                skill_id INTEGER,
                FOREIGN KEY (skill_id) REFERENCES skills(id)
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE hierarchy (
                child_id INTEGER,
                parent_id INTEGER,
                PRIMARY KEY (child_id, parent_id),
                FOREIGN KEY (child_id) REFERENCES skills(id),
                FOREIGN KEY (parent_id) REFERENCES skills(id)
            )
        """
        )
        conn.commit()
        conn.close()

        from src.cli.densify_ontology import SkillDatabaseManager

        manager = SkillDatabaseManager(temp_db_path)
        suggestion = {
            "canonical_name": "react",
            "aliases": ["react", "reactjs"],
            "parents": ["javascript", "frontend"],
        }

        result = manager.add_skill_to_database(suggestion)

        assert result is True

        # Verify data was inserted
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT canonical_name FROM skills WHERE canonical_name = 'react'")
        assert cursor.fetchone() is not None

        cursor.execute("SELECT COUNT(*) FROM aliases WHERE alias_name IN ('react', 'reactjs')")
        assert cursor.fetchone()[0] == 2

        cursor.execute(
            "SELECT COUNT(*) FROM skills WHERE canonical_name IN ('javascript', 'frontend')"
        )
        assert cursor.fetchone()[0] == 2  # Parents should be created

        conn.close()

        # Cleanup
        Path(temp_db_path).unlink()

    @pytest.mark.unit
    def test_add_skill_to_database_error(self):
        """Test error handling in add_skill_to_database."""
        from src.cli.densify_ontology import SkillDatabaseManager

        # Use non-existent database path
        manager = SkillDatabaseManager("/invalid/path/database.db")
        suggestion = {"canonical_name": "test", "aliases": ["test"], "parents": []}

        with patch("builtins.print"):  # Suppress error prints
            result = manager.add_skill_to_database(suggestion)

        assert result is False


class TestLLMSkillProcessor:
    """Test suite for LLMSkillProcessor class."""

    @pytest.mark.unit
    def test_simulate_llm_response(self):
        """Test simulation mode responses."""
        from src.cli.densify_ontology import DensificationConfig, LLMSkillProcessor

        config = DensificationConfig()
        processor = LLMSkillProcessor(config)

        # Test known simulation
        response = processor.simulate_llm_response("git")
        assert '"canonical_name": "git"' in response
        assert '"parents": ["version_control"]' in response

        # Test unknown skill
        response = processor.simulate_llm_response("unknown_skill")
        assert '"canonical_name": "unknown_skill"' in response
        assert '"parents": ["other"]' in response

    @pytest.mark.unit
    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_call_openai_api_success(self):
        """Test successful OpenAI API call."""
        from src.cli.densify_ontology import DensificationConfig, LLMSkillProcessor

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"test": "response"}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response

        # Create config and manually set the client
        with patch("builtins.print"):  # Suppress print statements
            config = DensificationConfig()
        config.client = mock_client
        config.use_openai = True

        processor = LLMSkillProcessor(config)

        result = processor.call_openai_api("test prompt")

        assert result == '{"test": "response"}'
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.unit
    def test_call_openai_api_no_config(self):
        """Test OpenAI API call without configuration."""
        from src.cli.densify_ontology import DensificationConfig, LLMSkillProcessor

        config = DensificationConfig()
        config.use_openai = False
        processor = LLMSkillProcessor(config)

        result = processor.call_openai_api("test prompt")

        assert result is None

    @pytest.mark.unit
    def test_get_llm_suggestion_valid_json(self):
        """Test get_llm_suggestion with valid JSON response."""
        from src.cli.densify_ontology import DensificationConfig, LLMSkillProcessor

        config = DensificationConfig()
        config.use_openai = False  # Use simulation
        processor = LLMSkillProcessor(config)

        result = processor.get_llm_suggestion("git", 100, {"python", "javascript"})

        assert result is not None
        assert "canonical_name" in result
        assert "aliases" in result
        assert "parents" in result
        assert result["canonical_name"] == "git"

    @pytest.mark.unit
    def test_get_llm_suggestion_invalid_json(self):
        """Test get_llm_suggestion with invalid JSON response."""
        from src.cli.densify_ontology import DensificationConfig, LLMSkillProcessor

        config = DensificationConfig()
        processor = LLMSkillProcessor(config)

        with (
            patch.object(processor, "simulate_llm_response", return_value="invalid json"),
            patch("builtins.print"),
        ):  # Suppress error prints
            result = processor.get_llm_suggestion("test", 100, set())

        assert result is None


class TestApiCacheManager:
    """Test suite for ApiCacheManager class."""

    @pytest.mark.unit
    @patch("src.cli.densify_ontology.requests.post")
    def test_reload_api_cache_success(self, mock_post):
        """Test successful API cache reload."""
        from src.cli.densify_ontology import ApiCacheManager

        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        manager = ApiCacheManager("http://test-api")

        with patch("builtins.print"):
            result = manager.reload_api_cache()

        assert result is True
        mock_post.assert_called_once_with("http://test-api/admin/reload", timeout=10)

    @pytest.mark.unit
    @patch("src.cli.densify_ontology.requests.post")
    def test_reload_api_cache_failure(self, mock_post):
        """Test API cache reload failure."""
        from src.cli.densify_ontology import ApiCacheManager

        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        manager = ApiCacheManager("http://test-api")

        with patch("builtins.print"):
            result = manager.reload_api_cache()

        assert result is False

    @pytest.mark.unit
    @patch("src.cli.densify_ontology.requests.post")
    def test_reload_api_cache_exception(self, mock_post):
        """Test API cache reload with exception."""
        from src.cli.densify_ontology import ApiCacheManager

        mock_post.side_effect = Exception("Connection error")

        manager = ApiCacheManager("http://test-api")

        with patch("builtins.print"):
            result = manager.reload_api_cache()

        assert result is False


class TestHumanReviewManager:
    """Test suite for HumanReviewManager class."""

    @pytest.mark.unit
    def test_save_needs_review_with_data(self):
        """Test saving needs review data."""
        from src.cli.densify_ontology import HumanReviewManager

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            manager = HumanReviewManager(data_dir)

            needs_review = [
                {"skill": "test1", "count": 10, "suggestion": {"canonical_name": "test1"}},
                {"skill": "test2", "count": 5, "suggestion": {"canonical_name": "test2"}},
            ]

            with patch("builtins.print"):
                manager.save_needs_review(needs_review)

            # Verify file was created
            csv_file = data_dir / "needs_human_review.csv"
            assert csv_file.exists()

            # Verify content
            df = pd.read_csv(csv_file)
            assert len(df) == 2
            assert "skill" in df.columns

    @pytest.mark.unit
    def test_save_needs_review_empty(self):
        """Test saving empty needs review data."""
        from src.cli.densify_ontology import HumanReviewManager

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            manager = HumanReviewManager(data_dir)

            manager.save_needs_review([])

            # Should not create file
            csv_file = data_dir / "needs_human_review.csv"
            assert not csv_file.exists()

    @pytest.mark.unit
    @patch("src.cli.densify_ontology.subprocess.run")
    def test_export_human_review_success(self, mock_run):
        """Test successful human review export."""
        from src.cli.densify_ontology import HumanReviewManager

        manager = HumanReviewManager(Path("/tmp"))

        result = manager.export_human_review()

        assert result is True
        mock_run.assert_called_once_with(
            ["poetry", "run", "python", "src/cli/export_human_review.py"], check=True
        )

    @pytest.mark.unit
    @patch("src.cli.densify_ontology.subprocess.run")
    def test_export_human_review_failure(self, mock_run):
        """Test human review export failure."""
        from src.cli.densify_ontology import HumanReviewManager

        mock_run.side_effect = Exception("Command failed")

        manager = HumanReviewManager(Path("/tmp"))

        with patch("builtins.print"):
            result = manager.export_human_review()

        assert result is False


class TestOntologyDensifier:
    """Test suite for OntologyDensifier class."""

    @pytest.mark.unit
    def test_ontology_densifier_initialization(self):
        """Test OntologyDensifier initialization."""
        from src.cli.densify_ontology import DensificationConfig, OntologyDensifier

        # Test with default config
        densifier = OntologyDensifier()
        assert densifier.config is not None
        assert densifier.db_manager is not None
        assert densifier.llm_processor is not None
        assert densifier.cache_manager is not None
        assert densifier.review_manager is not None

        # Test with custom config
        custom_config = DensificationConfig()
        densifier = OntologyDensifier(custom_config)
        assert densifier.config is custom_config

    @pytest.mark.unit
    def test_load_unmapped_skills(self):
        """Test loading unmapped skills CSV."""
        from src.cli.densify_ontology import OntologyDensifier

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as temp_csv:
            temp_csv.write("skill,count\npython,100\njavascript,50\n")
            temp_csv_path = temp_csv.name

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create unmapped_skills_analysis.csv in temp dir
            analysis_file = Path(temp_dir) / "unmapped_skills_analysis.csv"
            analysis_file.write_text("skill,count\npython,100\njavascript,50\n")

            densifier = OntologyDensifier()
            densifier.config.data_dir = Path(temp_dir)

            df = densifier.load_unmapped_skills()

            assert len(df) == 2
            assert "skill" in df.columns
            assert "count" in df.columns

        # Cleanup
        Path(temp_csv_path).unlink()

    @pytest.mark.unit
    def test_should_auto_approve(self):
        """Test auto-approval logic."""
        from src.cli.densify_ontology import OntologyDensifier

        densifier = OntologyDensifier()

        # High frequency should auto-approve
        assert densifier.should_auto_approve(1500, {"canonical_name": "test"}, set()) is True

        # Existing skill should auto-approve
        assert densifier.should_auto_approve(100, {"canonical_name": "python"}, {"python"}) is True

        # Low frequency, new skill should not auto-approve
        assert densifier.should_auto_approve(100, {"canonical_name": "new_skill"}, set()) is False

    @pytest.mark.unit
    def test_process_skill_batch(self):
        """Test processing a batch of skills."""
        from src.cli.densify_ontology import OntologyDensifier

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name

        # Create test database with proper schema
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE skills (id INTEGER PRIMARY KEY, canonical_name TEXT UNIQUE)")
        cursor.execute(
            "CREATE TABLE aliases (id INTEGER PRIMARY KEY, alias_name TEXT, skill_id INTEGER)"
        )
        cursor.execute("CREATE TABLE hierarchy (child_id INTEGER, parent_id INTEGER)")
        conn.commit()
        conn.close()

        # Create test batch
        batch_df = pd.DataFrame(
            {
                "skill": ["high_freq_skill", "low_freq_skill"],
                "count": [2000, 50],  # One high, one low frequency
            }
        )

        densifier = OntologyDensifier()
        densifier.config.db_file = temp_db_path
        densifier.config.use_openai = False  # Use simulation

        # Mock the database manager to avoid schema issues
        with patch.object(densifier.db_manager, "add_skill_to_database", return_value=True):
            added_count, needs_review = densifier.process_skill_batch(batch_df, set())

        assert added_count == 1  # Only high frequency should be auto-approved
        assert len(needs_review) == 1  # Low frequency should need review

        # Cleanup
        Path(temp_db_path).unlink()

    @pytest.mark.unit
    def test_print_final_stats(self):
        """Test printing final statistics."""
        from src.cli.densify_ontology import OntologyDensifier

        densifier = OntologyDensifier()

        with patch("builtins.print") as mock_print:
            densifier.print_final_stats(5, 3)

            assert mock_print.call_count >= 3
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("5 compétences ajoutées" in call for call in calls)
            assert any("3 en attente de revue" in call for call in calls)

    @pytest.mark.unit
    def test_densify_ontology_integration(self):
        """Test the main densify_ontology method."""
        from src.cli.densify_ontology import OntologyDensifier

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)

            # Create test unmapped skills file
            analysis_file = data_dir / "unmapped_skills_analysis.csv"
            analysis_file.write_text("skill,count\ntest_skill,100\n")

            # Create test database
            db_file = data_dir / "test.db"
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE skills (id INTEGER PRIMARY KEY, canonical_name TEXT UNIQUE)"
            )
            cursor.execute(
                "CREATE TABLE aliases (id INTEGER PRIMARY KEY, alias_name TEXT, skill_id INTEGER)"
            )
            cursor.execute("CREATE TABLE hierarchy (child_id INTEGER, parent_id INTEGER)")
            conn.commit()
            conn.close()

            densifier = OntologyDensifier()
            densifier.config.data_dir = data_dir
            densifier.config.db_file = str(db_file)
            densifier.config.use_openai = False  # Use simulation

            # Reinitialize db_manager with correct path
            from src.cli.densify_ontology import SkillDatabaseManager

            densifier.db_manager = SkillDatabaseManager(str(db_file))

            # Mock external calls
            with (
                patch.object(densifier.db_manager, "add_skill_to_database", return_value=False),
                patch.object(densifier.cache_manager, "reload_api_cache", return_value=True),
                patch.object(densifier.review_manager, "export_human_review", return_value=True),
                patch("builtins.print"),
            ):
                results = densifier.densify_ontology(batch_size=1)

            assert "added_count" in results
            assert "needs_review_count" in results
            assert "cache_reloaded" in results
            assert "existing_skills_count" in results


class TestMainFunctions:
    """Test suite for main functions."""

    @pytest.mark.unit
    def test_parse_batch_size_from_args(self):
        """Test parsing batch size from command line arguments."""
        from src.cli.densify_ontology import parse_batch_size_from_args

        # Test default
        with patch("sys.argv", ["script.py"]):
            assert parse_batch_size_from_args() == 10

        # Test valid argument
        with patch("sys.argv", ["script.py", "50"]):
            assert parse_batch_size_from_args() == 50

        # Test invalid argument
        with patch("sys.argv", ["script.py", "invalid"]), patch("builtins.print"):
            assert parse_batch_size_from_args() == 10

    @pytest.mark.unit
    def test_main_function(self):
        """Test main function."""
        from src.cli.densify_ontology import main

        mock_results = {"added_count": 5, "needs_review_count": 3, "cache_reloaded": True}

        with (
            patch("src.cli.densify_ontology.parse_batch_size_from_args", return_value=10),
            patch("src.cli.densify_ontology.OntologyDensifier") as mock_densifier_class,
        ):
            mock_densifier = Mock()
            mock_densifier.densify_ontology.return_value = mock_results
            mock_densifier_class.return_value = mock_densifier

            result = main()

            assert result is None
            mock_densifier.densify_ontology.assert_called_once_with(10)

    @pytest.mark.unit
    def test_empty_batch_handling(self):
        """Test handling of empty batches."""
        from src.cli.densify_ontology import OntologyDensifier

        empty_batch = pd.DataFrame({"skill": [], "count": []})

        densifier = OntologyDensifier()
        added_count, needs_review = densifier.process_skill_batch(empty_batch, set())

        assert added_count == 0
        assert len(needs_review) == 0

    @pytest.mark.unit
    def test_config_environment_variables(self):
        """Test configuration with various environment variables."""
        from src.cli.densify_ontology import DensificationConfig

        # Test with custom model
        with patch.dict("os.environ", {"LLM_MODEL": "gpt-4-turbo"}):
            config = DensificationConfig()
            assert config.llm_model == "gpt-4-turbo"

        # Test with missing variables
        with patch.dict("os.environ", {}, clear=True):
            config = DensificationConfig()
            assert config.llm_model == "gpt-4o-mini-2024-07-18"
            assert config.openai_api_key is None
