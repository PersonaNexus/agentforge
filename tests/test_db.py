"""Tests for the database persistence layer."""

from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentforge.web.db.engine import init_db
from agentforge.web.db.models import Base, JobRow, IdentityRow, ExtractionRow, CultureProfileRow
from agentforge.web.db.repository import (
    JobRepository,
    IdentityRepository,
    ExtractionRepository,
    CultureRepository,
)
from agentforge.web.jobs import Job, JobStore


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def db_store(session_factory):
    return JobStore(session_factory=session_factory)


# ------------------------------------------------------------------
# Engine & Init
# ------------------------------------------------------------------


class TestEngine:
    def test_init_db_creates_tables(self, db_engine):
        inspector = db_engine.dialect.get_table_names(
            db_engine.connect()
        ) if hasattr(db_engine.dialect, 'get_table_names') else []
        # Alternative check: try to query
        from sqlalchemy import inspect as sa_inspect
        insp = sa_inspect(db_engine)
        tables = insp.get_table_names()
        assert "jobs" in tables
        assert "identities" in tables
        assert "extractions" in tables
        assert "culture_profiles" in tables
        assert "batch_runs" in tables


# ------------------------------------------------------------------
# Job Repository
# ------------------------------------------------------------------


class TestJobRepository:
    def test_create_job(self, db_session):
        repo = JobRepository(db_session)
        row = repo.create(job_id="abc123", job_type="forge", source_filename="test.txt")
        assert row.id == "abc123"
        assert row.job_type == "forge"
        assert row.status == "pending"

    def test_get_job(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="xyz789", job_type="import")
        row = repo.get("xyz789")
        assert row is not None
        assert row.job_type == "import"

    def test_get_missing_job(self, db_session):
        repo = JobRepository(db_session)
        assert repo.get("nonexistent") is None

    def test_update_result(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="upd001", job_type="forge")
        repo.update_result("upd001", status="done", result={"key": "value"})
        row = repo.get("upd001")
        assert row.status == "done"
        assert row.completed_at is not None
        assert json.loads(row.result_json) == {"key": "value"}

    def test_update_error(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="err001", job_type="forge")
        repo.update_result("err001", status="error", error="boom")
        row = repo.get("err001")
        assert row.status == "error"
        assert row.error == "boom"

    def test_list_all(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="j001", job_type="forge")
        repo.create(job_id="j002", job_type="import")
        repo.create(job_id="j003", job_type="batch")
        jobs = repo.list_all()
        assert len(jobs) == 3

    def test_list_filter_by_type(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="j010", job_type="forge")
        repo.create(job_id="j011", job_type="import")
        jobs = repo.list_all(job_type="forge")
        assert len(jobs) == 1
        assert jobs[0]["job_type"] == "forge"

    def test_list_filter_by_status(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="j020", job_type="forge")
        repo.update_result("j020", status="done", result={})
        repo.create(job_id="j021", job_type="forge")
        jobs = repo.list_all(status="done")
        assert len(jobs) == 1

    def test_get_count(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="c001", job_type="forge")
        repo.create(job_id="c002", job_type="forge")
        assert repo.get_count() == 2
        assert repo.get_count(job_type="import") == 0

    def test_mark_stale_running(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="stale1", job_type="forge")
        row = repo.get("stale1")
        row.status = "running"
        db_session.commit()

        count = repo.mark_stale_running_as_error()
        assert count == 1

        row = repo.get("stale1")
        assert row.status == "error"
        assert "Server restarted" in row.error

    def test_get_full_result(self, db_session):
        repo = JobRepository(db_session)
        repo.create(job_id="fr001", job_type="forge")
        repo.update_result("fr001", status="done", result={"skills": [1, 2, 3]})
        result = repo.get_full_result("fr001")
        assert result == {"skills": [1, 2, 3]}

    def test_pagination(self, db_session):
        repo = JobRepository(db_session)
        for i in range(10):
            repo.create(job_id=f"pg{i:03d}", job_type="forge")
        page1 = repo.list_all(offset=0, limit=3)
        page2 = repo.list_all(offset=3, limit=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0]["id"] != page2[0]["id"]


# ------------------------------------------------------------------
# Identity Repository
# ------------------------------------------------------------------


class TestIdentityRepository:
    def test_save_and_get(self, db_session):
        repo = IdentityRepository(db_session)
        row = repo.save(
            name="Test Agent",
            identity_yaml="schema_version: '1.0'\n",
            source="forge",
            extraction_json={"role": {"title": "Test"}},
        )
        assert row.id
        assert row.name == "Test Agent"

        full = repo.get_full(row.id)
        assert full is not None
        assert full["name"] == "Test Agent"
        assert full["extraction_json"] == {"role": {"title": "Test"}}

    def test_list_all(self, db_session):
        repo = IdentityRepository(db_session)
        repo.save(name="Agent A", identity_yaml="a", source="forge")
        repo.save(name="Agent B", identity_yaml="b", source="import")
        identities = repo.list_all()
        assert len(identities) == 2

    def test_search(self, db_session):
        repo = IdentityRepository(db_session)
        repo.save(name="Data Engineer", identity_yaml="a", source="forge")
        repo.save(name="Product Manager", identity_yaml="b", source="forge")
        results = repo.list_all(search="engineer")
        assert len(results) == 1
        assert "Engineer" in results[0]["name"]

    def test_delete(self, db_session):
        repo = IdentityRepository(db_session)
        row = repo.save(name="Deleteme", identity_yaml="x", source="forge")
        assert repo.delete(row.id)
        assert repo.get_full(row.id) is None

    def test_delete_nonexistent(self, db_session):
        repo = IdentityRepository(db_session)
        assert not repo.delete("nonexistent")

    def test_search_escapes_like_wildcards(self, db_session):
        """Ensure % and _ in search terms are treated literally, not as wildcards."""
        repo = IdentityRepository(db_session)
        repo.save(name="100% Effective Agent", identity_yaml="a", source="forge")
        repo.save(name="Normal Agent", identity_yaml="b", source="forge")

        # Searching for "%" should only match the name containing a literal %
        results = repo.list_all(search="100%")
        assert len(results) == 1
        assert "100%" in results[0]["name"]

        # "_" should not act as a single-char wildcard
        repo.save(name="A_B Agent", identity_yaml="c", source="forge")
        results = repo.list_all(search="A_B")
        assert len(results) == 1
        assert "A_B" in results[0]["name"]

    def test_search_length_capped(self, db_session):
        """Search strings longer than 200 chars are truncated."""
        repo = IdentityRepository(db_session)
        repo.save(name="Agent", identity_yaml="a", source="forge")
        # Should not raise even with a very long search string
        results = repo.list_all(search="x" * 500)
        assert isinstance(results, list)


# ------------------------------------------------------------------
# Extraction Repository
# ------------------------------------------------------------------


class TestExtractionRepository:
    def test_save_and_get(self, db_session):
        repo = ExtractionRepository(db_session)
        row = repo.save(
            role_title="Senior Dev",
            domain="Engineering",
            extraction_json={"skills": []},
            coverage_score=0.85,
        )
        result = repo.get(row.id)
        assert result is not None
        assert result["role_title"] == "Senior Dev"
        assert result["coverage_score"] == 0.85

    def test_list_all(self, db_session):
        repo = ExtractionRepository(db_session)
        repo.save(role_title="A", domain="X", extraction_json={})
        repo.save(role_title="B", domain="Y", extraction_json={})
        assert len(repo.list_all()) == 2


# ------------------------------------------------------------------
# Culture Repository
# ------------------------------------------------------------------


class TestCultureRepository:
    def test_save_and_get(self, db_session):
        repo = CultureRepository(db_session)
        row = repo.save(
            name="Startup Culture",
            description="Move fast",
            profile_json={"values": []},
            source_file="startup.yaml",
        )
        result = repo.get(row.id)
        assert result is not None
        assert result["name"] == "Startup Culture"
        assert result["profile_json"] == {"values": []}

    def test_list_and_delete(self, db_session):
        repo = CultureRepository(db_session)
        row = repo.save(name="Corp", profile_json={})
        assert len(repo.list_all()) == 1
        repo.delete(row.id)
        assert len(repo.list_all()) == 0


# ------------------------------------------------------------------
# JobStore (Dual-Store)
# ------------------------------------------------------------------


class TestJobStoreDualStore:
    def test_create_persists_to_db(self, db_store, session_factory):
        job = db_store.create(job_type="forge", source_filename="test.txt")
        with session_factory() as session:
            row = session.get(JobRow, job.id)
            assert row is not None
            assert row.job_type == "forge"
            assert row.source_filename == "test.txt"

    def test_emit_done_persists_result(self, db_store, session_factory):
        job = db_store.create(job_type="forge")
        job.emit_done({"identity_yaml": "test", "blueprint": {}})

        with session_factory() as session:
            row = session.get(JobRow, job.id)
            assert row.status == "done"
            result = json.loads(row.result_json)
            assert result["identity_yaml"] == "test"

    def test_emit_error_persists(self, db_store, session_factory):
        job = db_store.create(job_type="forge")
        job.emit_error("something broke")

        with session_factory() as session:
            row = session.get(JobRow, job.id)
            assert row.status == "error"
            assert row.error == "something broke"

    def test_get_from_memory(self, db_store):
        job = db_store.create()
        retrieved = db_store.get(job.id)
        assert retrieved is job  # Same in-memory object

    def test_get_from_db_after_eviction(self, db_store, session_factory):
        """Simulate server restart: job not in memory, loaded from DB."""
        job = db_store.create(job_type="forge")
        job.emit_done({"data": "preserved"})

        # Clear in-memory cache (simulates restart)
        db_store._jobs.clear()

        # Should fall through to DB
        loaded = db_store.get(job.id)
        assert loaded is not None
        assert loaded.status == "done"
        assert loaded.result["data"] == "preserved"

    def test_get_nonexistent(self, db_store):
        assert db_store.get("nope") is None

    def test_persist_result_explicit(self, db_store, session_factory):
        job = db_store.create()
        job.status = "done"
        job.result = {"explicit": True}
        db_store.persist_result(job)

        with session_factory() as session:
            row = session.get(JobRow, job.id)
            result = json.loads(row.result_json)
            assert result["explicit"] is True

    def test_recover_stale_jobs(self, session_factory):
        # Directly insert a "running" job
        with session_factory() as session:
            session.add(JobRow(id="stale_run", status="running", job_type="forge"))
            session.commit()

        store = JobStore(session_factory=session_factory)
        count = store.recover_stale_jobs()
        assert count == 1

        with session_factory() as session:
            row = session.get(JobRow, "stale_run")
            assert row.status == "error"

    def test_cleanup_only_removes_from_memory(self, db_store, session_factory):
        job = db_store.create()
        job.emit_done({"result": True})

        # Force job to appear old
        job.created_at = time.time() - 3600

        removed = db_store.cleanup()
        assert removed == 1
        assert db_store._jobs.get(job.id) is None

        # But it's still in the DB
        with session_factory() as session:
            row = session.get(JobRow, job.id)
            assert row is not None


# ------------------------------------------------------------------
# JobStore without DB (backward compat)
# ------------------------------------------------------------------


class TestJobStoreInMemoryOnly:
    def test_create_without_db(self):
        store = JobStore()
        job = store.create()
        assert job.id
        assert store.get(job.id) is job

    def test_emit_done_without_db(self):
        store = JobStore()
        job = store.create()
        job.emit_done({"test": True})
        assert job.status == "done"

    def test_cleanup_without_db(self):
        store = JobStore()
        job = store.create()
        job.created_at = time.time() - 3600
        assert store.cleanup() == 1

    def test_persist_result_noop_without_db(self):
        store = JobStore()
        job = store.create()
        job.result = {"x": 1}
        store.persist_result(job)  # Should not raise


# ------------------------------------------------------------------
# History API Routes
# ------------------------------------------------------------------


class TestHistoryRoutes:
    @pytest.fixture
    def client(self):
        import os
        os.environ["AGENTFORGE_DATABASE_URL"] = "sqlite:///:memory:"
        from agentforge.web.app import create_app
        from starlette.testclient import TestClient

        app = create_app()
        yield TestClient(app)
        os.environ.pop("AGENTFORGE_DATABASE_URL", None)

    def test_list_jobs_empty(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["jobs"] == []
        assert body["total"] == 0

    def test_list_identities_empty(self, client):
        resp = client.get("/api/identities")
        assert resp.status_code == 200
        assert resp.json()["identities"] == []

    def test_list_extractions_empty(self, client):
        resp = client.get("/api/extractions")
        assert resp.status_code == 200
        assert resp.json()["extractions"] == []

    def test_list_culture_profiles_empty(self, client):
        resp = client.get("/api/culture-profiles")
        assert resp.status_code == 200
        assert resp.json()["profiles"] == []

    def test_invalid_status_filter_rejected(self, client):
        resp = client.get("/api/jobs?status=hacked")
        assert resp.status_code == 422

    def test_invalid_job_type_filter_rejected(self, client):
        resp = client.get("/api/jobs?job_type=DROP_TABLE")
        assert resp.status_code == 422

    def test_valid_status_filter_accepted(self, client):
        resp = client.get("/api/jobs?status=done")
        assert resp.status_code == 200

    def test_get_job_404(self, client):
        resp = client.get("/api/jobs/aabbccddee11")
        assert resp.status_code == 404

    def test_get_identity_404(self, client):
        resp = client.get("/api/identities/aabbccddee1122334455667788")
        assert resp.status_code == 404

    def test_delete_identity_404(self, client):
        resp = client.delete("/api/identities/aabbccddee1122334455667788")
        assert resp.status_code == 404

    def test_invalid_id_format_rejected(self, client):
        """Non-hex IDs should be rejected with 422."""
        resp = client.get("/api/jobs/not-valid!")
        assert resp.status_code == 422

        resp = client.get("/api/identities/ZZZZZZZZZZZZZZZZ")
        assert resp.status_code == 422

        resp = client.delete("/api/identities/xss-attempt-here")
        assert resp.status_code == 422

        resp = client.get("/api/extractions/sql-injection-test")
        assert resp.status_code == 422

    def test_forge_creates_job_in_db(self, client):
        """Import identity should create a DB job and identity."""
        from agentforge.generation.identity_generator import IdentityGenerator

        # Generate a valid identity YAML
        from tests.conftest import _make_sample_extraction
        extraction = _make_sample_extraction()
        generator = IdentityGenerator()
        _, yaml_str = generator.generate(extraction)

        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", yaml_str.encode(), "text/yaml")},
            data={"output_format": "claude_code"},
        )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        # Job should appear in history
        jobs_resp = client.get("/api/jobs")
        assert jobs_resp.status_code == 200
        job_ids = [j["id"] for j in jobs_resp.json()["jobs"]]
        assert job_id in job_ids

        # Identity should be saved
        ids_resp = client.get("/api/identities")
        assert ids_resp.status_code == 200
        assert len(ids_resp.json()["identities"]) >= 1

    def test_reload_job(self, client):
        """Reload a job that exists in DB."""
        from agentforge.generation.identity_generator import IdentityGenerator
        from tests.conftest import _make_sample_extraction

        extraction = _make_sample_extraction()
        generator = IdentityGenerator()
        _, yaml_str = generator.generate(extraction)

        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", yaml_str.encode(), "text/yaml")},
            data={"output_format": "claude_code"},
        )
        job_id = resp.json()["job_id"]

        reload_resp = client.get(f"/api/jobs/{job_id}/reload")
        assert reload_resp.status_code == 200
        assert reload_resp.json()["job_id"] == job_id
