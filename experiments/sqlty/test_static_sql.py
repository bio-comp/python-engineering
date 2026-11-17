"""SQLTy static query and schema-drift controls, isolated and database-free."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DDL_REQUIRED = "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL);\n"
DDL_OPTIONAL = "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);\n"
VALID = """\
import sqlite3

from sqlty import SQL

conn = sqlite3.connect(":memory:")
query = SQL[tuple[int, str]]("--sql\\nSELECT id, email FROM users WHERE id = ?")
conn.execute(query, (1,))
"""
INVALID = """\
import sqlite3

from sqlty import SQL

conn = sqlite3.connect(":memory:")
query = SQL[tuple[int, str]]("--sql\\nSELECT id, emial FROM users WHERE id = ?")
conn.execute(query, (1, 2))
"""
VALID_NULLABLE = """\
import sqlite3

from sqlty import SQL

conn = sqlite3.connect(":memory:")
query = SQL[tuple[int, str | None]]("--sql\\nSELECT id, email FROM users WHERE id = ?")
conn.execute(query, (1,))
"""


def _check(tmp_path: Path, ddl: str, code: str) -> tuple[int, set[str]]:
    executable = shutil.which("sqlty")
    assert executable is not None, "SQLTy pinned optional dependency group required"
    schema = tmp_path / "schema.sql"
    source = tmp_path / "query.py"
    schema.write_text(ddl)
    source.write_text(code)
    result = subprocess.run(
        [
            executable,
            "check",
            "--isolated",
            "--dialect",
            "sqlite",
            "--schema",
            str(schema),
            "--error",
            "unknown-column",
            "--output-format",
            "json",
            str(source),
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode in (0, 1), result.stderr
    messages = json.loads(result.stdout)
    return result.returncode, {
        message["rule"] for message in messages if message["severity"] == "error"
    }


def test_valid_query_and_correct_parameter_count(tmp_path: Path) -> None:
    assert _check(tmp_path, DDL_REQUIRED, VALID) == (0, set())


def test_seeded_unknown_column_and_wrong_parameter_count(tmp_path: Path) -> None:
    rc, rules = _check(tmp_path, DDL_REQUIRED, INVALID)
    assert rc == 1
    assert rules == {"unknown-column", "param-count-mismatch"}


def test_nullable_migration_fails_prior_annotation(tmp_path: Path) -> None:
    rc, rules = _check(tmp_path, DDL_OPTIONAL, VALID)
    assert rc == 1
    assert "narrow-type" in rules


def test_corrected_nullable_annotation_passes(tmp_path: Path) -> None:
    assert _check(tmp_path, DDL_OPTIONAL, VALID_NULLABLE) == (0, set())


@pytest.mark.parametrize("ddl", [DDL_REQUIRED, DDL_OPTIONAL])
def test_nullable_and_nonnullable_definitions_are_distinct(ddl: str) -> None:
    assert ("NOT NULL" in ddl) == (ddl == DDL_REQUIRED)
