"""Pytest fixtures — isolated SQLite DB for unit and API tests.

Each test gets a fresh database under a temporary directory:

1. Call ``noosphere.core.db.close()`` so the module-level ``_conn`` is cleared.
2. Patch ``DATA_DIR`` / ``DB_PATH`` on ``noosphere.core.config`` (and on
   ``noosphere.core.db`` — required because ``db`` binds those names at import
   time, so updating only ``config`` would leave ``get_conn()`` using stale
   paths).
3. Call ``get_conn()`` to create the DB file and apply schema.
4. Yield to the test.
5. Call ``close()`` again; pytest removes the per-test ``tmp_path`` subtree.

``NOOSPHERE_DATA_DIR`` is also set so any code that reads the env sees the
same location.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import noosphere.core.config as core_config
import noosphere.core.db as core_db
from noosphere.api.main import app


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fresh SQLite DB per test; resets ``core_db`` connection cache."""
    core_db.close()

    data_dir = tmp_path / "noosphere_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "noosphere.db"

    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(data_dir))
    monkeypatch.setattr(core_config, "DATA_DIR", data_dir)
    monkeypatch.setattr(core_config, "DB_PATH", db_path)
    monkeypatch.setattr(core_db, "DATA_DIR", data_dir)
    monkeypatch.setattr(core_db, "DB_PATH", db_path)

    core_db.get_conn()
    yield
    core_db.close()


@pytest.fixture
def client(isolated_db):
    with TestClient(app) as c:
        yield c
