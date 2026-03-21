"""FastAPI application factory for the AgentForge web UI."""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agentforge import __version__
from agentforge.web.jobs import JobStore

logger = logging.getLogger(__name__)

_WEB_DIR = Path(__file__).parent
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATES_DIR = _WEB_DIR / "templates"


def _start_cleanup_thread(store: JobStore) -> None:
    """Periodically clean up expired jobs."""

    def _loop() -> None:
        while True:
            time.sleep(300)
            store.cleanup()

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def _init_database() -> tuple:
    """Initialize database engine and session factory.

    Returns (engine, session_factory) or (None, None) if DB deps are missing.
    """
    try:
        from agentforge.web.db.engine import get_engine, get_session_factory, init_db

        engine = get_engine()
        init_db(engine)
        session_factory = get_session_factory(engine)
        logger.info("Database initialized: %s", engine.url)
        return engine, session_factory
    except ImportError:
        logger.warning("SQLAlchemy not installed — running without database persistence")
        return None, None
    except Exception:
        logger.exception("Failed to initialize database — running without persistence")
        return None, None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="AgentForge",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
    )

    # Initialize database
    engine, session_factory = _init_database()
    app.state.engine = engine
    app.state.db_session_factory = session_factory

    # Create job store with DB persistence
    store = JobStore(session_factory=session_factory)
    app.state.jobs = store

    # Shared thread pool for forge/batch workers (prevents unbounded thread creation)
    max_workers = int(os.environ.get("AGENTFORGE_MAX_WORKERS", "4"))
    app.state.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="forge")

    # Recover any jobs stuck in "running" from a previous crash
    recovered = store.recover_stale_jobs()
    if recovered:
        logger.info("Recovered %d stale jobs from previous run", recovered)

    _start_cleanup_thread(store)

    # Add security middleware (order matters: auth first, then rate limit)
    from agentforge.web.auth import BearerAuthMiddleware
    from agentforge.web.rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BearerAuthMiddleware)

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Register route modules
    from agentforge.web.routes import batch, culture, extract, forge, pages, settings

    app.include_router(pages.router)
    app.include_router(extract.router, prefix="/api")
    app.include_router(forge.router, prefix="/api")
    app.include_router(batch.router, prefix="/api")
    app.include_router(culture.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    # Tools API
    from agentforge.web.routes import tools

    app.include_router(tools.router, prefix="/api")

    # History API
    from agentforge.web.routes import history

    app.include_router(history.router, prefix="/api")

    return app
