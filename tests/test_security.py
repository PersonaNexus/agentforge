"""Tests for security hardening: API key validation, LLM error handling, input validation."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentforge.utils import safe_filename, safe_output_path, safe_rel_path


class TestAPIKeyValidation:
    def test_empty_key_raises(self):
        from agentforge.llm.client import LLMClient
        from agentforge.config import AgentForgeConfig

        old_ant = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_oai = os.environ.pop("OPENAI_API_KEY", None)
        try:
            empty_config = AgentForgeConfig(api_key="")
            with patch("agentforge.config.load_config", return_value=empty_config):
                with pytest.raises(ValueError, match="No API key found"):
                    LLMClient()
        finally:
            if old_ant is not None:
                os.environ["ANTHROPIC_API_KEY"] = old_ant
            if old_oai is not None:
                os.environ["OPENAI_API_KEY"] = old_oai

    def test_explicit_anthropic_key_used(self):
        from agentforge.llm.client import LLMClient

        # sk-ant- prefix → Anthropic provider, default Anthropic model
        client = LLMClient(api_key="sk-ant-test-key-123")
        assert client.provider == "anthropic"
        assert client.model == "claude-sonnet-4-20250514"

    def test_explicit_openai_key_used(self):
        from agentforge.llm.client import LLMClient

        # Non sk-ant- prefix → OpenAI provider, default OpenAI model
        client = LLMClient(api_key="sk-test-key-123")
        assert client.provider == "openai"
        assert client.model == "gpt-4o"

    def test_env_key_used(self):
        from agentforge.llm.client import LLMClient

        old_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-env-key-456"
        try:
            client = LLMClient()
            assert client.provider == "anthropic"
            assert client.model == "claude-sonnet-4-20250514"
        finally:
            if old_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = old_key
            else:
                os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_openai_env_key_used(self):
        from agentforge.llm.client import LLMClient

        old_ant = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_oai = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-env-openai-key"
        try:
            client = LLMClient()
            assert client.provider == "openai"
            assert client.model == "gpt-4o"
        finally:
            if old_ant is not None:
                os.environ["ANTHROPIC_API_KEY"] = old_ant
            if old_oai is not None:
                os.environ["OPENAI_API_KEY"] = old_oai
            else:
                os.environ.pop("OPENAI_API_KEY", None)


class TestLLMRetry:
    def test_retry_on_rate_limit(self):
        import anthropic
        from agentforge.llm.client import LLMClient

        client = LLMClient(api_key="sk-ant-test", provider="anthropic")
        mock_response = MagicMock()
        mock_response.content = []

        # Simulate rate limit then success
        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.side_effect = [
            anthropic.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            ),
            mock_response,
        ]

        with patch("agentforge.llm.client.time.sleep"):
            result = client._call_anthropic_with_retry(model="test", messages=[], max_tokens=10)

        assert result == mock_response
        assert client._anthropic_client.messages.create.call_count == 2

    def test_auth_error_raises_immediately(self):
        import anthropic
        from agentforge.llm.client import LLMClient

        client = LLMClient(api_key="sk-ant-bad", provider="anthropic")
        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.side_effect = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401, headers={}),
            body=None,
        )

        with pytest.raises(ValueError, match="Invalid Anthropic API key"):
            client._call_anthropic_with_retry(model="test", messages=[], max_tokens=10)

        # Should not retry on auth error
        assert client._anthropic_client.messages.create.call_count == 1

    def test_api_status_error_raises(self):
        import anthropic
        from agentforge.llm.client import LLMClient

        client = LLMClient(api_key="sk-ant-test", provider="anthropic")
        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.side_effect = anthropic.APIStatusError(
            message="server error",
            response=MagicMock(status_code=500, headers={}),
            body=None,
        )

        with pytest.raises(RuntimeError, match="LLM request failed"):
            client._call_anthropic_with_retry(model="test", messages=[], max_tokens=10)

    def test_max_retries_exhausted(self):
        import anthropic
        from agentforge.llm.client import LLMClient

        client = LLMClient(api_key="sk-ant-test", provider="anthropic")
        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429, headers={}),
            body=None,
        )

        with patch("agentforge.llm.client.time.sleep"):
            with pytest.raises(RuntimeError, match="after 3 retries"):
                client._call_anthropic_with_retry(model="test", messages=[], max_tokens=10)


class TestPathTraversal:
    def test_traversal_in_agent_id(self, tmp_path):
        """Path traversal characters should be stripped from filenames."""
        result = safe_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

        path = safe_output_path(tmp_path, f"{result}.yaml")
        assert str(path).startswith(str(tmp_path.resolve()))

    def test_backslash_traversal(self):
        result = safe_filename("..\\..\\windows\\system32")
        assert "\\" not in result

    def test_safe_output_stays_in_dir(self, tmp_path):
        path = safe_output_path(tmp_path, "normal_agent.yaml")
        assert path.parent == tmp_path

    def test_safe_rel_path_normal(self, tmp_path):
        """Normal relative paths should resolve within base_dir."""
        tmp_path.mkdir(exist_ok=True)
        result = safe_rel_path(tmp_path, "instructions/voice.md")
        assert str(result).startswith(str(tmp_path.resolve()))
        assert result.name == "voice.md"

    def test_safe_rel_path_traversal_blocked(self, tmp_path):
        """Path traversal in rel_path should be blocked."""
        tmp_path.mkdir(exist_ok=True)
        # safe_rel_path sanitizes each component, so ../../ gets stripped
        result = safe_rel_path(tmp_path, "../../etc/passwd")
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_safe_rel_path_backslash_traversal(self, tmp_path):
        """Backslash traversal should be sanitized."""
        tmp_path.mkdir(exist_ok=True)
        result = safe_rel_path(tmp_path, "..\\..\\windows\\system32")
        assert str(result).startswith(str(tmp_path.resolve()))


class TestMCPPathValidation:
    def test_mcp_rejects_non_jd_extensions(self):
        """MCP forge_file should reject non-JD file types."""
        from agentforge.mcp_server import _ALLOWED_MCP_EXTENSIONS

        assert ".py" not in _ALLOWED_MCP_EXTENSIONS
        assert ".yaml" not in _ALLOWED_MCP_EXTENSIONS
        assert ".txt" in _ALLOWED_MCP_EXTENSIONS
        assert ".pdf" in _ALLOWED_MCP_EXTENSIONS
        assert ".docx" in _ALLOWED_MCP_EXTENSIONS


class TestUploadSizeLimits:
    def test_extract_route_has_size_check(self):
        """Verify the extract route enforces upload size limits."""
        import inspect
        from agentforge.web.routes.extract import extract

        source = inspect.getsource(extract)
        assert "_MAX_UPLOAD_BYTES" in source
        assert "413" in source


class TestInputValidation:
    def test_pdf_size_limit(self, tmp_path):
        """PDF ingestion should reject files over 50MB."""
        from agentforge.ingestion.pdf import _MAX_PDF_SIZE_MB

        # Create a file that appears large (mock stat)
        big_file = tmp_path / "huge.pdf"
        big_file.write_text("x")  # Just needs to exist

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = (_MAX_PDF_SIZE_MB + 1) * 1024 * 1024
            with pytest.raises(ValueError, match="too large"):
                from agentforge.ingestion.pdf import ingest_pdf
                ingest_pdf(big_file)

    def test_culture_empty_yaml(self, tmp_path):
        """Empty culture YAML should raise clear error."""
        from agentforge.mapping.culture_mapper import CultureParser

        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")

        parser = CultureParser()
        with pytest.raises(ValueError, match="empty or not a valid"):
            parser.parse_yaml(empty_file)

    def test_culture_list_yaml(self, tmp_path):
        """Culture YAML that's a list (not mapping) should raise."""
        from agentforge.mapping.culture_mapper import CultureParser

        list_file = tmp_path / "list.yaml"
        list_file.write_text("- item1\n- item2\n")

        parser = CultureParser()
        with pytest.raises(ValueError, match="empty or not a valid"):
            parser.parse_yaml(list_file)

    def test_text_encoding_fallback(self, tmp_path):
        """Text ingestion should fall back to latin-1 for non-UTF-8 files."""
        from agentforge.ingestion.text import ingest_file

        # Write a file with latin-1 encoded content
        latin_file = tmp_path / "latin.txt"
        latin_file.write_bytes("Résumé: Senior Développeur\nExperience: 5+ years".encode("latin-1"))

        jd = ingest_file(latin_file)
        assert "Senior" in jd.raw_text


class TestPDFIngestion:
    def test_pdf_ingestion(self, tmp_path):
        """Test basic PDF ingestion with a real PDF."""
        import fitz

        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Senior Software Engineer\n\nRequirements:\n- Python\n- 5+ years")
        doc.save(str(pdf_path))
        doc.close()

        from agentforge.ingestion.pdf import ingest_pdf
        jd = ingest_pdf(pdf_path)
        assert "Software Engineer" in jd.raw_text
        assert jd.metadata["format"] == "pdf"
        assert jd.metadata["page_count"] == 1

    def test_pdf_file_not_found(self):
        from agentforge.ingestion.pdf import ingest_pdf
        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            ingest_pdf("/nonexistent/file.pdf")

    def test_pdf_corrupted(self, tmp_path):
        """Corrupted PDF should raise ValueError."""
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_text("not a pdf")

        from agentforge.ingestion.pdf import ingest_pdf
        with pytest.raises(ValueError, match="Failed to open PDF"):
            ingest_pdf(bad_pdf)

    def test_pdf_empty_content(self, tmp_path):
        """PDF with no text should raise ValueError."""
        import fitz

        pdf_path = tmp_path / "empty.pdf"
        doc = fitz.open()
        doc.new_page()  # blank page
        doc.save(str(pdf_path))
        doc.close()

        from agentforge.ingestion.pdf import ingest_pdf
        with pytest.raises(ValueError, match="No text content"):
            ingest_pdf(pdf_path)


class TestExtractStructured:
    def test_extract_structured_success(self):
        """Test extract_structured with mocked Anthropic API response."""
        from pydantic import BaseModel
        from agentforge.llm.client import LLMClient

        class SimpleOutput(BaseModel):
            name: str
            score: float

        client = LLMClient(api_key="sk-ant-test", provider="anthropic")
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "SimpleOutput"
        mock_block.input = {"name": "test", "score": 0.9}

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.return_value = mock_response

        result = client.extract_structured(
            prompt="Extract data",
            output_schema=SimpleOutput,
        )
        assert result.name == "test"
        assert result.score == 0.9

    def test_extract_structured_with_system(self):
        """Test extract_structured passes system prompt."""
        from pydantic import BaseModel
        from agentforge.llm.client import LLMClient

        class SimpleOutput(BaseModel):
            value: int

        client = LLMClient(api_key="sk-ant-test", provider="anthropic")
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "SimpleOutput"
        mock_block.input = {"value": 42}

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.return_value = mock_response

        result = client.extract_structured(
            prompt="Extract",
            output_schema=SimpleOutput,
            system="Be precise",
        )
        assert result.value == 42
        call_kwargs = client._anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "Be precise"

    def test_extract_structured_no_tool_use(self):
        """Should raise if no tool use found in response."""
        from pydantic import BaseModel
        from agentforge.llm.client import LLMClient

        class Dummy(BaseModel):
            x: int

        client = LLMClient(api_key="sk-ant-test", provider="anthropic")
        mock_block = MagicMock()
        mock_block.type = "text"

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.return_value = mock_response

        with pytest.raises(ValueError, match="No Dummy tool use found"):
            client.extract_structured(prompt="test", output_schema=Dummy)

    def test_extract_structured_openai_success(self):
        """Test extract_structured with mocked OpenAI API response."""
        from pydantic import BaseModel
        from agentforge.llm.client import LLMClient

        class SimpleOutput(BaseModel):
            name: str
            score: float

        client = LLMClient(api_key="sk-test-key", provider="openai")

        mock_func = MagicMock()
        mock_func.arguments = '{"name": "test", "score": 0.9}'
        mock_tool_call = MagicMock()
        mock_tool_call.function = mock_func
        mock_choice = MagicMock()
        mock_choice.message.tool_calls = [mock_tool_call]
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        client._openai_client = MagicMock()
        client._openai_client.chat.completions.create.return_value = mock_response

        result = client.extract_structured(
            prompt="Extract data",
            output_schema=SimpleOutput,
        )
        assert result.name == "test"
        assert result.score == 0.9

    def test_connection_error_retry(self):
        """Connection errors should be retried."""
        import anthropic
        from agentforge.llm.client import LLMClient

        client = LLMClient(api_key="sk-ant-test", provider="anthropic")
        mock_response = MagicMock()
        mock_response.content = []

        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.side_effect = [
            anthropic.APIConnectionError(request=MagicMock()),
            mock_response,
        ]

        with patch("agentforge.llm.client.time.sleep"):
            result = client._call_anthropic_with_retry(model="test", messages=[], max_tokens=10)

        assert result == mock_response
        assert client._anthropic_client.messages.create.call_count == 2

    def test_config_fallback_for_api_key(self):
        """LLMClient should fall back to config file for API key."""
        from agentforge.llm.client import LLMClient
        from agentforge.config import AgentForgeConfig

        old_ant = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_oai = os.environ.pop("OPENAI_API_KEY", None)
        try:
            mock_config = AgentForgeConfig(api_key="sk-ant-from-config")
            with patch("agentforge.config.load_config", return_value=mock_config):
                client = LLMClient()
                assert client.provider == "anthropic"
                assert client.model == "claude-sonnet-4-20250514"
        finally:
            if old_ant is not None:
                os.environ["ANTHROPIC_API_KEY"] = old_ant
            if old_oai is not None:
                os.environ["OPENAI_API_KEY"] = old_oai


class TestBearerAuthMiddleware:
    def test_no_token_configured_allows_all(self):
        """When no token is set, requests pass through."""
        from agentforge.web.auth import _get_api_token

        old = os.environ.pop("AGENTFORGE_API_TOKEN", None)
        try:
            with patch("agentforge.config.load_config") as mock_cfg:
                mock_cfg.return_value = MagicMock(web_api_token=None)
                token = _get_api_token()
                assert token is None
        finally:
            if old is not None:
                os.environ["AGENTFORGE_API_TOKEN"] = old

    def test_env_token_used(self):
        """Environment variable AGENTFORGE_API_TOKEN should be picked up."""
        from agentforge.web.auth import _get_api_token

        old = os.environ.get("AGENTFORGE_API_TOKEN")
        os.environ["AGENTFORGE_API_TOKEN"] = "test-secret-123"
        try:
            token = _get_api_token()
            assert token == "test-secret-123"
        finally:
            if old is not None:
                os.environ["AGENTFORGE_API_TOKEN"] = old
            else:
                os.environ.pop("AGENTFORGE_API_TOKEN", None)

    def test_disabled_token(self):
        """Setting token to 'disabled' should return 'disabled'."""
        from agentforge.web.auth import _get_api_token

        old = os.environ.get("AGENTFORGE_API_TOKEN")
        os.environ["AGENTFORGE_API_TOKEN"] = "disabled"
        try:
            token = _get_api_token()
            assert token == "disabled"
        finally:
            if old is not None:
                os.environ["AGENTFORGE_API_TOKEN"] = old
            else:
                os.environ.pop("AGENTFORGE_API_TOKEN", None)


class TestRateLimiter:
    def test_sliding_window_allows_under_limit(self):
        """Requests under the limit should be allowed."""
        from agentforge.web.rate_limit import _SlidingWindowCounter

        limiter = _SlidingWindowCounter(max_requests=3, window_seconds=60)
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is True

    def test_sliding_window_blocks_over_limit(self):
        """Requests over the limit should be blocked."""
        from agentforge.web.rate_limit import _SlidingWindowCounter

        limiter = _SlidingWindowCounter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is False

    def test_sliding_window_per_client(self):
        """Different clients should have independent limits."""
        from agentforge.web.rate_limit import _SlidingWindowCounter

        limiter = _SlidingWindowCounter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client2") is True
        assert limiter.is_allowed("client1") is False

    def test_cleanup_removes_stale_entries(self):
        """Cleanup should remove entries past the window."""
        from agentforge.web.rate_limit import _SlidingWindowCounter

        limiter = _SlidingWindowCounter(max_requests=1, window_seconds=0)
        limiter.is_allowed("client1")
        limiter.cleanup()
        assert "client1" not in limiter._requests


class TestPromptInjectionDefenses:
    def test_extraction_prompt_has_boundary_tags(self):
        """Extraction prompt should use XML boundary tags for user content."""
        from agentforge.extraction.prompts import EXTRACTION_PROMPT

        assert "<job_description>" in EXTRACTION_PROMPT
        assert "</job_description>" in EXTRACTION_PROMPT
        assert "untrusted" in EXTRACTION_PROMPT.lower()

    def test_methodology_prompt_has_boundary_tags(self):
        """Methodology user context should use XML boundary tags."""
        from agentforge.extraction.prompts import METHODOLOGY_USER_CONTEXT_WITH_EXAMPLES

        assert "<user_examples>" in METHODOLOGY_USER_CONTEXT_WITH_EXAMPLES
        assert "<user_frameworks>" in METHODOLOGY_USER_CONTEXT_WITH_EXAMPLES
        assert "untrusted" in METHODOLOGY_USER_CONTEXT_WITH_EXAMPLES.lower()

    def test_refine_prompt_has_boundary_tags(self):
        """Refine prompt should use XML boundary tags for feedback."""
        from agentforge.refinement.refiner import REFINE_PROMPT

        assert "<user_feedback>" in REFINE_PROMPT
        assert "</user_feedback>" in REFINE_PROMPT
        assert "untrusted" in REFINE_PROMPT.lower()

    def test_jd_text_truncated(self):
        """SkillExtractor should truncate excessively long JD text."""
        from agentforge.extraction.skill_extractor import SkillExtractor

        assert SkillExtractor._MAX_JD_CHARS == 50_000


class TestThreadPoolCap:
    def test_app_has_executor(self):
        """The app should have a bounded thread pool executor."""
        from agentforge.web.app import create_app

        app = create_app()
        assert hasattr(app.state, "executor")
        assert app.state.executor._max_workers <= 10  # reasonable cap
