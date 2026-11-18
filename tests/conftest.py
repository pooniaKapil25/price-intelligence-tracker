"""Isolate integration tests from the user's real SQLite database and API."""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATABASE = PROJECT_ROOT / "price_tracker.db"
fd, TEST_DATABASE_NAME = tempfile.mkstemp(prefix="pti_pytest_", suffix=".db")
os.close(fd)
TEST_DATABASE = Path(TEST_DATABASE_NAME)

if SOURCE_DATABASE.exists():
    shutil.copyfile(SOURCE_DATABASE, TEST_DATABASE)

# Environment variables take precedence over .env, so the app imports below
# use only this disposable copy and cannot mutate the user's database.
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"


def _table_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("products", "price_history")
            if table in tables
        }
    finally:
        connection.close()


def _table_columns(path: Path) -> dict[str, list[tuple]]:
    if not path.exists():
        return {}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            table: [tuple(row) for row in connection.execute(f'PRAGMA table_info("{table}")')]
            for table in ("products", "price_history")
            if table in tables
        }
    finally:
        connection.close()


ORIGINAL_DATABASE_COUNTS = _table_counts(SOURCE_DATABASE)
ORIGINAL_DATABASE_COLUMNS = _table_columns(SOURCE_DATABASE)


@pytest.fixture(scope="session")
def test_database_path() -> Path:
    return TEST_DATABASE


def pytest_unconfigure(config) -> None:
    """Dispose the test engine and remove only the disposable database copy."""
    database_module = __import__("sys").modules.get("backend.database")
    if database_module is not None:
        database_module.engine.dispose()
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{TEST_DATABASE}{suffix}").unlink(missing_ok=True)
