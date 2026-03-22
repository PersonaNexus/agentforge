"""Tests for culture parsing, mixin conversion, and pipeline integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agentforge.mapping.culture_mapper import CultureMixinConverter, CultureParser
from agentforge.models.culture import CultureProfile, CultureValue
from agentforge.models.tool_profile import AgentToolProfile
from agentforge.pipeline.stages import CultureStage


TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "agentforge" / "templates" / "cultures"


# --- CultureProfile model tests ---


class TestCultureModel:
    def test_culture_value_basic(self):
        val = CultureValue(
            name="Innovation",
            description="Think creatively",
            behavioral_indicators=["Experiment often", "Challenge norms"],
            trait_deltas={"creativity": 0.2, "assertiveness": 0.1},
        )
        assert val.name == "Innovation"
        assert len(val.behavioral_indicators) == 2
        assert val.trait_deltas["creativity"] == 0.2

    def test_culture_value_defaults(self):
        val = CultureValue(name="Simple")
        assert val.description == ""
        assert val.behavioral_indicators == []
        assert val.trait_deltas == {}

    def test_culture_profile_basic(self):
        profile = CultureProfile(
            name="Test Corp",
            description="A test culture",
            values=[CultureValue(name="Speed", trait_deltas={"assertiveness": 0.15})],
            communication_tone="direct and energetic",
            decision_style="fast consensus",
        )
        assert profile.name == "Test Corp"
        assert len(profile.values) == 1
        assert profile.communication_tone == "direct and energetic"

    def test_culture_profile_defaults(self):
        profile = CultureProfile(name="Minimal")
        assert profile.values == []
        assert profile.communication_tone is None
        assert profile.source_file is None


# --- CultureParser tests ---


class TestCultureParser:
    def test_parse_yaml_startup(self):
        parser = CultureParser()
        profile = parser.parse_yaml(TEMPLATES_DIR / "startup_innovative.yaml")

        assert profile.name == "Innovative Startup"
        assert len(profile.values) == 3
        assert profile.communication_tone == "direct, energetic, and informal"
        assert profile.decision_style == "fast consensus with strong owner"

        # Check trait deltas for "Move Fast"
        move_fast = profile.values[0]
        assert move_fast.name == "Move Fast"
        assert move_fast.trait_deltas["assertiveness"] == 0.15
        assert move_fast.trait_deltas["patience"] == -0.1

    def test_parse_yaml_enterprise(self):
        parser = CultureParser()
        profile = parser.parse_yaml(TEMPLATES_DIR / "enterprise_collaborative.yaml")

        assert profile.name == "Enterprise Collaborative"
        assert len(profile.values) == 3

        collab = profile.values[0]
        assert collab.name == "Collaboration"
        assert collab.trait_deltas["warmth"] == 0.15

    def test_parse_yaml_customer_centric(self):
        parser = CultureParser()
        profile = parser.parse_yaml(TEMPLATES_DIR / "customer_centric.yaml")

        assert profile.name == "Customer-Centric"
        assert len(profile.values) == 3
        assert profile.values[0].trait_deltas["empathy"] == 0.2

    def test_parse_yaml_sets_source_file(self):
        parser = CultureParser()
        profile = parser.parse_yaml(TEMPLATES_DIR / "startup_innovative.yaml")
        assert profile.source_file is not None
        assert "startup_innovative" in profile.source_file

    def test_parse_yaml_file_not_found(self):
        parser = CultureParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_yaml("/nonexistent/path/culture.yaml")

    def test_parse_file_auto_detects_yaml(self):
        parser = CultureParser()
        profile = parser.parse_file(TEMPLATES_DIR / "startup_innovative.yaml")
        assert profile.name == "Innovative Startup"

    def test_parse_text_via_llm(self):
        """Test freeform text parsing with mocked LLM client."""
        mock_profile = CultureProfile(
            name="Extracted Corp",
            description="LLM-extracted culture",
            values=[
                CultureValue(
                    name="Teamwork",
                    description="Work together",
                    trait_deltas={"warmth": 0.1},
                ),
            ],
            communication_tone="friendly",
        )

        mock_client = MagicMock()
        mock_client.extract_structured.return_value = mock_profile

        parser = CultureParser(llm_client=mock_client)
        result = parser.parse_text("We value teamwork above all else.", source="test.md")

        assert result.name == "Extracted Corp"
        assert result.source_file == "test.md"
        mock_client.extract_structured.assert_called_once()

    def test_parse_markdown_calls_llm(self, tmp_path):
        """Test markdown file parsing delegates to LLM."""
        md_file = tmp_path / "culture.md"
        md_file.write_text("# Our Culture\nWe value innovation and speed.")

        mock_profile = CultureProfile(
            name="MD Corp",
            values=[CultureValue(name="Innovation", trait_deltas={"creativity": 0.2})],
        )
        mock_client = MagicMock()
        mock_client.extract_structured.return_value = mock_profile

        parser = CultureParser(llm_client=mock_client)
        result = parser.parse_markdown(md_file)

        assert result.name == "MD Corp"
        assert result.source_file is not None

    def test_parse_file_auto_detects_markdown(self, tmp_path):
        """Test parse_file dispatches markdown to LLM path."""
        md_file = tmp_path / "culture.md"
        md_file.write_text("# Culture\nWe are innovative.")

        mock_profile = CultureProfile(name="Auto Corp", values=[])
        mock_client = MagicMock()
        mock_client.extract_structured.return_value = mock_profile

        parser = CultureParser(llm_client=mock_client)
        result = parser.parse_file(md_file)
        assert result.name == "Auto Corp"


# --- CultureMixinConverter tests ---


class TestCultureMixinConverter:
    def _sample_profile(self) -> CultureProfile:
        return CultureProfile(
            name="Test Culture",
            description="A test culture profile",
            values=[
                CultureValue(
                    name="Innovation",
                    description="Embrace creative solutions",
                    behavioral_indicators=["Experiment boldly", "Challenge status quo"],
                    trait_deltas={"creativity": 0.2, "assertiveness": 0.1},
                ),
                CultureValue(
                    name="Empathy",
                    description="Understand others deeply",
                    behavioral_indicators=["Listen actively", "Ask clarifying questions"],
                    trait_deltas={"empathy": 0.15, "warmth": 0.1, "creativity": 0.05},
                ),
            ],
            communication_tone="creative and empathetic",
        )

    def test_convert_produces_valid_yaml(self):
        converter = CultureMixinConverter()
        yaml_str = converter.convert(self._sample_profile())

        data = yaml.safe_load(yaml_str)
        assert data["schema_version"] == "1.0"
        assert "mixin" in data

    def test_mixin_id_and_name(self):
        converter = CultureMixinConverter()
        yaml_str = converter.convert(self._sample_profile())
        data = yaml.safe_load(yaml_str)

        assert data["mixin"]["id"] == "culture_test_culture"
        assert data["mixin"]["name"] == "Test Culture Culture"

    def test_aggregated_traits(self):
        converter = CultureMixinConverter()
        yaml_str = converter.convert(self._sample_profile())
        data = yaml.safe_load(yaml_str)

        traits = data["personality"]["traits"]
        # creativity: 0.5 + 0.2 = 0.7, then 0.7 + 0.05 = 0.75
        assert traits["creativity"] == 0.75
        # assertiveness: 0.5 + 0.1 = 0.6
        assert traits["assertiveness"] == 0.6
        # empathy: 0.5 + 0.15 = 0.65
        assert traits["empathy"] == 0.65
        # warmth: 0.5 + 0.1 = 0.6
        assert traits["warmth"] == 0.6

    def test_communication_tone(self):
        converter = CultureMixinConverter()
        yaml_str = converter.convert(self._sample_profile())
        data = yaml.safe_load(yaml_str)

        assert data["communication"]["tone"]["default"] == "creative and empathetic"

    def test_no_communication_when_none(self):
        profile = CultureProfile(name="No Tone", values=[])
        converter = CultureMixinConverter()
        yaml_str = converter.convert(profile)
        data = yaml.safe_load(yaml_str)

        assert "communication" not in data

    def test_principles_from_values(self):
        converter = CultureMixinConverter()
        yaml_str = converter.convert(self._sample_profile())
        data = yaml.safe_load(yaml_str)

        assert "principles" in data
        assert len(data["principles"]) == 2
        assert data["principles"][0]["priority"] == 10
        assert data["principles"][1]["priority"] == 11
        assert "implications" in data["principles"][0]

    def test_convert_and_save(self, tmp_path):
        converter = CultureMixinConverter()
        output = tmp_path / "mixin.yaml"
        result = converter.convert_and_save(self._sample_profile(), output)

        assert result == output
        assert output.exists()
        data = yaml.safe_load(output.read_text())
        assert data["mixin"]["id"] == "culture_test_culture"

    def test_trait_clamping(self):
        """Traits should be clamped to 0-1 range."""
        profile = CultureProfile(
            name="Extreme",
            values=[
                CultureValue(name="V1", trait_deltas={"creativity": 0.3}),
                CultureValue(name="V2", trait_deltas={"creativity": 0.3}),
            ],
        )
        converter = CultureMixinConverter()
        yaml_str = converter.convert(profile)
        data = yaml.safe_load(yaml_str)

        # 0.5 + 0.3 = 0.8, then 0.8 + 0.3 = 1.1 → clamped to 1.0
        assert data["personality"]["traits"]["creativity"] == 1.0

    def test_empty_values_no_personality(self):
        profile = CultureProfile(name="Empty", values=[])
        converter = CultureMixinConverter()
        yaml_str = converter.convert(profile)
        data = yaml.safe_load(yaml_str)

        assert "personality" not in data
        assert "principles" not in data


# --- CultureStage tests ---


class TestCultureStage:
    def test_culture_stage_with_yaml_path(self):
        """CultureStage loads YAML culture file and applies trait deltas."""
        stage = CultureStage()
        context = {
            "culture_path": str(TEMPLATES_DIR / "startup_innovative.yaml"),
            "traits": {
                "warmth": 0.5,
                "assertiveness": 0.5,
                "directness": 0.5,
                "creativity": 0.5,
                "patience": 0.5,
                "epistemic_humility": 0.5,
            },
        }

        result = stage.run(context)

        assert "culture_profile" in result
        assert result["culture_profile"].name == "Innovative Startup"
        assert "culture_mixin_yaml" in result

        # Startup culture boosts assertiveness (+0.15)
        assert result["traits"]["assertiveness"] == 0.65
        # Startup culture boosts directness (+0.1 from Move Fast + 0.15 from Radical Transparency)
        assert result["traits"]["directness"] == 0.75
        # Startup culture reduces patience (-0.1)
        assert result["traits"]["patience"] == 0.4

    def test_culture_stage_no_culture_passthrough(self):
        """CultureStage without culture_path or profile is a no-op."""
        stage = CultureStage()
        context = {"traits": {"warmth": 0.5}}

        result = stage.run(context)

        assert "culture_profile" not in result
        assert result["traits"]["warmth"] == 0.5

    def test_culture_stage_with_existing_profile(self):
        """CultureStage uses an existing culture_profile from context."""
        profile = CultureProfile(
            name="Preloaded",
            values=[
                CultureValue(name="Focus", trait_deltas={"rigor": 0.2}),
            ],
        )
        stage = CultureStage()
        context = {
            "culture_profile": profile,
            "traits": {"rigor": 0.6},
        }

        result = stage.run(context)
        assert result["traits"]["rigor"] == 0.8
        assert "culture_mixin_yaml" in result

    def test_culture_stage_trait_clamping(self):
        """Traits should be clamped after culture delta application."""
        profile = CultureProfile(
            name="Extreme",
            values=[
                CultureValue(name="Push", trait_deltas={"assertiveness": 0.3}),
                CultureValue(name="Push More", trait_deltas={"assertiveness": 0.3}),
            ],
        )
        stage = CultureStage()
        context = {
            "culture_profile": profile,
            "traits": {"assertiveness": 0.8},
        }

        result = stage.run(context)
        assert result["traits"]["assertiveness"] == 1.0  # clamped

    def test_culture_stage_adds_missing_traits(self):
        """Culture deltas for traits not in the context should start from 0.5."""
        profile = CultureProfile(
            name="Add Traits",
            values=[
                CultureValue(name="New", trait_deltas={"humor": 0.1}),
            ],
        )
        stage = CultureStage()
        context = {"culture_profile": profile, "traits": {}}

        result = stage.run(context)
        # humor starts at 0.5 (default get), then +0.1 = 0.6
        assert result["traits"]["humor"] == 0.6

    def test_default_pipeline_includes_culture(self):
        """Default pipeline should include culture stage."""
        from agentforge.pipeline.forge_pipeline import ForgePipeline
        pipeline = ForgePipeline.default()
        names = [s.name for s in pipeline.stages]
        assert "culture" in names
        assert names == ["ingest", "anonymize", "extract", "methodology", "map", "culture", "generate", "tool_map", "analyze", "team_compose"]

    def test_pipeline_with_culture_and_mocked_extraction(self, fixtures_dir):
        """Full pipeline with culture applied via mocked extraction."""
        from agentforge.pipeline.forge_pipeline import ForgePipeline
        from agentforge.models.extracted_skills import (
            ExtractionResult, ExtractedRole, ExtractedSkill,
            SkillCategory, SkillProficiency, SuggestedTraits,
        )

        pipeline = ForgePipeline.default()

        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Support Agent",
                purpose="Help customers",
                scope_primary=["Customer support"],
                audience=["Customers"],
                seniority="mid",
                domain="support",
            ),
            skills=[
                ExtractedSkill(
                    name="Communication", category=SkillCategory.SOFT,
                    proficiency=SkillProficiency.ADVANCED, importance="required",
                    context="Customer interactions",
                ),
            ],
            responsibilities=["Resolve customer issues"],
            suggested_traits=SuggestedTraits(empathy=0.8, patience=0.7),
            automation_potential=0.3,
            automation_rationale="Requires human empathy",
        )

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = extraction

        from agentforge.models.extracted_skills import MethodologyExtraction
        mock_methodology_extractor = MagicMock()
        mock_methodology_extractor.extract.return_value = MethodologyExtraction()

        mock_tool_mapper = MagicMock()
        mock_tool_mapper.map_tools.return_value = AgentToolProfile()

        context = {
            "input_path": str(fixtures_dir / "customer_success_manager.txt"),
            "extractor": mock_extractor,
            "methodology_extractor": mock_methodology_extractor,
            "tool_mapper": mock_tool_mapper,
            "culture_path": str(TEMPLATES_DIR / "customer_centric.yaml"),
        }

        context = pipeline.run(context)

        assert "culture_profile" in context
        assert context["culture_profile"].name == "Customer-Centric"
        assert "culture_mixin_yaml" in context
        assert "identity" in context
        assert "identity_yaml" in context
