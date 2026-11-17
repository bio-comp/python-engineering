# E-011 — SQLTy 0.6.0 raw SQL static checks

Offline static checks; **no database is opened or contacted by the tests**.
The Python snippets are embedded strings and are not imported or executed.
SQLTy reads temporary synthetic SQLite DDL and annotated query strings.

Positive: valid typed query and corrected nullable type.
Negative: misspelled column, extra bound parameter, and making an originally
non-nullable column nullable without updating its Python row annotation.

    uv run --locked --group sqlty-lab pytest -q experiments/sqlty/test_static_sql.py

SQLTy 0.6.0 is confined to an optional experimental dependency group and a
dedicated PR-CI check. No application code or mandatory Python SDLC is changed.
This proves only narrow static diagnostic behavior. Compare mypy/Ruff,
invalid-but-parseable dynamic queries, actual driver behavior and false
positives before claiming usable default protection.
