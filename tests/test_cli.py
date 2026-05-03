"""Tests for the AgentForge CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    SkillCategory,
    SkillProficiency,
    SuggestedTraits,
)

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "agentforge" / "templates" / "cultures"


def _mock_extraction() -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title="Test Engineer",
            purpose="Test software systems",
            scope_primary=["Testing", "QA"],
            audience=["Developers"],
            seniority="mid",
            domain="engineering",
        ),
        skills=[
            ExtractedSkill(
                name="Python", category=SkillCategory.HARD,
                proficiency=SkillProficiency.ADVANCED, importance="required",
                context="Test automation",
            ),
            ExtractedSkill(
                name="Communication", category=SkillCategory.SOFT,
                importance="required", context="Team work",
            ),
        ],
        responsibilities=["Write tests", "Review code"],
        suggested_traits=SuggestedTraits(rigor=0.8, patience=0.7),
        automation_potential=0.5,
        automation_rationale="Partially automatable",
    )


class TestVersionCommand:
    def test_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "AgentForge v" in result.output


class TestExtractCommand:
    def test_file_not_found(self):
        result = runner.invoke(app, ["extract", "/nonexistent/file.txt"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    @patch("agentforge.cli._make_client")
    def test_extract_success(self, mock_make_client):
        mock_client = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()
        mock_make_client.return_value = mock_client

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "extract",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--quiet",
            ])

        assert result.exit_code == 0
        assert "Extracted" in result.output

    @patch("agentforge.cli._make_client")
    def test_extract_json_format(self, mock_make_client):
        mock_client = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()
        mock_make_client.return_value = mock_client

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "extract",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--format", "json",
                "--quiet",
            ])

        assert result.exit_code == 0

    @patch("agentforge.cli._make_client")
    def test_extract_with_output(self, mock_make_client, tmp_path):
        mock_client = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()
        mock_make_client.return_value = mock_client

        output_file = tmp_path / "result.yaml"

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "extract",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--output", str(output_file),
                "--quiet",
            ])

        assert result.exit_code == 0
        assert output_file.exists()


class TestForgeCommand:
    def test_file_not_found(self):
        result = runner.invoke(app, ["forge", "/nonexistent/file.txt"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_culture_file_not_found(self):
        result = runner.invoke(app, [
            "forge",
            str(FIXTURES_DIR / "senior_data_engineer.txt"),
            "--culture", "/nonexistent/culture.yaml",
        ])
        assert result.exit_code == 1
        assert "Culture file not found" in result.output

    @patch("agentforge.cli._make_client")
    def test_forge_quick_mode(self, mock_make_client, tmp_path):
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--quick",
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        assert "forged successfully" in result.output


class TestCultureCommands:
    def test_culture_list(self):
        result = runner.invoke(app, ["culture", "list"])
        assert result.exit_code == 0
        assert "Built-in Culture Templates" in result.output
        assert "startup_innovative" in result.output

    def test_culture_parse_file_not_found(self):
        result = runner.invoke(app, ["culture", "parse", "/nonexistent/culture.yaml"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_culture_to_mixin_file_not_found(self):
        result = runner.invoke(app, ["culture", "to-mixin", "/nonexistent/culture.yaml"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_culture_to_mixin_success(self):
        result = runner.invoke(app, [
            "culture", "to-mixin",
            str(TEMPLATES_DIR / "startup_innovative.yaml"),
        ])
        assert result.exit_code == 0
        assert "PersonaNexus Mixin" in result.output

    def test_culture_to_mixin_with_output(self, tmp_path):
        output = tmp_path / "mixin.yaml"
        result = runner.invoke(app, [
            "culture", "to-mixin",
            str(TEMPLATES_DIR / "startup_innovative.yaml"),
            "--output", str(output),
        ])
        assert result.exit_code == 0
        assert output.exists()
        data = yaml.safe_load(output.read_text())
        assert "mixin" in data


class TestBatchCommand:
    def test_directory_not_found(self):
        result = runner.invoke(app, ["batch", "/nonexistent/dir"])
        assert result.exit_code == 1
        assert "Directory not found" in result.output

    def test_empty_directory(self, tmp_path):
        result = runner.invoke(app, ["batch", str(tmp_path)])
        assert result.exit_code == 1
        assert "No JD files found" in result.output


class TestIngestFile:
    def test_ingest_text_file(self):
        from agentforge.cli import _ingest_file
        jd = _ingest_file(FIXTURES_DIR / "senior_data_engineer.txt")
        assert jd.title
        assert len(jd.raw_text) > 0

    def test_ingest_docx_dispatches(self, tmp_path):
        """Test that .docx extension dispatches to docx ingester."""
        from agentforge.cli import _ingest_file
        from docx import Document

        docx_path = tmp_path / "test.docx"
        doc = Document()
        doc.add_paragraph("Senior Developer position")
        doc.save(str(docx_path))

        jd = _ingest_file(docx_path)
        assert "developer" in jd.raw_text.lower()


class TestForgeDefaultMode:
    @patch("agentforge.cli._make_client")
    def test_forge_default_mode(self, mock_make_client, tmp_path):
        """Forge with default pipeline (full stages)."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        assert "forged successfully" in result.output

    @patch("agentforge.cli._make_client")
    def test_forge_deep_mode(self, mock_make_client, tmp_path):
        """Forge with --deep flag uses deep analysis."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--deep",
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        assert "forged successfully" in result.output

    @patch("agentforge.cli._make_client")
    def test_forge_with_culture(self, mock_make_client, tmp_path):
        """Forge with --culture flag applies culture profile."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--culture", str(TEMPLATES_DIR / "startup_innovative.yaml"),
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        assert "forged successfully" in result.output

    @patch("agentforge.cli._make_client")
    def test_forge_no_skill_file(self, mock_make_client, tmp_path):
        """Forge with --no-skill-file skips SKILL.md generation."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--quick",
                "--no-skill-file",
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        skill_files = list(tmp_path.glob("*_SKILL.md"))
        assert len(skill_files) == 0

    @patch("agentforge.cli._make_client")
    def test_forge_target_plain_skips_identity_yaml(self, mock_make_client, tmp_path):
        """`--target plain` writes no identity.yaml by default."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--quick",
                "--target", "plain",
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        yaml_files = list(tmp_path.glob("*.yaml"))
        assert yaml_files == []
        assert "identity.yaml suppressed" in result.output

    @patch("agentforge.cli._make_client")
    def test_forge_target_plain_keep_identity_yaml(self, mock_make_client, tmp_path):
        """`--target plain --keep-identity-yaml` re-enables the yaml write."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--quick",
                "--target", "plain",
                "--keep-identity-yaml",
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        yaml_files = list(tmp_path.glob("*.yaml"))
        assert len(yaml_files) == 1

    def test_forge_target_unknown_value_rejected(self, tmp_path):
        """An unrecognized --target value fails fast with a clear message."""
        result = runner.invoke(app, [
            "forge",
            str(FIXTURES_DIR / "senior_data_engineer.txt"),
            "--target", "bogus",
            "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 1
        assert "Unknown --target" in result.output

    @patch("agentforge.cli._make_client")
    def test_forge_target_default_writes_identity_yaml(self, mock_make_client, tmp_path):
        """Default target (claude-code) still writes identity.yaml — back-compat."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "forge",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--quick",
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code == 0
        yaml_files = list(tmp_path.glob("*.yaml"))
        assert len(yaml_files) == 1


class TestExtractVerbose:
    @patch("agentforge.cli._make_client")
    def test_extract_verbose(self, mock_make_client):
        """Test --verbose flag enables debug logging."""
        mock_client = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()
        mock_make_client.return_value = mock_client

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "extract",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
                "--verbose",
                "--quiet",
            ])

        assert result.exit_code == 0

    @patch("agentforge.cli._make_client")
    def test_extract_display_output(self, mock_make_client):
        """Test extract without --quiet shows rich display."""
        mock_client = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()
        mock_make_client.return_value = mock_client

        with patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=mock_extractor):
            result = runner.invoke(app, [
                "extract",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
            ])

        assert result.exit_code == 0
        # Should show role and skills tables
        assert "Test Engineer" in result.output
        assert "Python" in result.output


class TestExtractErrorHandling:
    @patch("agentforge.cli._make_client")
    def test_extraction_error_shows_panel(self, mock_make_client):
        """Extraction errors should show a rich error panel."""
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client

        with patch(
            "agentforge.extraction.skill_extractor.SkillExtractor",
            side_effect=RuntimeError("LLM connection failed"),
        ):
            result = runner.invoke(app, [
                "extract",
                str(FIXTURES_DIR / "senior_data_engineer.txt"),
            ])

        assert result.exit_code == 1
        assert "Extraction Failed" in result.output or "LLM connection failed" in result.output


class TestInitCommand:
    def test_init_command(self):
        """Test init command with mocked prompts."""
        with patch("agentforge.config.save_config") as mock_save, \
             patch("agentforge.config.load_config", side_effect=Exception("no config")), \
             patch("anthropic.Anthropic"):
            result = runner.invoke(app, ["init"], input=(
                "sk-test-key\n"
                "claude-sonnet-4-20250514\n"
                ".\n"
                "1\n"
                "\n"
            ))

        # Init should complete (validation may fail but setup works)
        assert "Welcome to AgentForge Setup" in result.output


class TestIngestPDF:
    def test_ingest_pdf_via_cli(self, tmp_path):
        """Test that _ingest_file dispatches to PDF ingestion."""
        import fitz
        from agentforge.cli import _ingest_file

        pdf_path = tmp_path / "job.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Data Engineer Position\n\nRequirements:\n- SQL\n- Python")
        doc.save(str(pdf_path))
        doc.close()

        jd = _ingest_file(pdf_path)
        assert "Data Engineer" in jd.raw_text


class TestMakeClient:
    def test_missing_api_key_shows_hint(self):
        """Test that missing API key shows helpful error."""
        import os
        from unittest.mock import patch
        from agentforge.config import AgentForgeConfig

        old_ant = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_oai = os.environ.pop("OPENAI_API_KEY", None)
        try:
            # Also mock config to return empty key so config file fallback is blocked
            empty_config = AgentForgeConfig(api_key="")
            with patch("agentforge.config.load_config", return_value=empty_config):
                result = runner.invoke(app, ["extract", str(FIXTURES_DIR / "senior_data_engineer.txt")])
            assert result.exit_code == 1
            # The error panel should mention init or API key env vars
            assert "init" in result.output.lower() or "API_KEY" in result.output
        finally:
            if old_ant is not None:
                os.environ["ANTHROPIC_API_KEY"] = old_ant
            if old_oai is not None:
                os.environ["OPENAI_API_KEY"] = old_oai
