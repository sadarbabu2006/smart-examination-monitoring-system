"""SQLite connection and schema management helpers."""

import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    """Return the request-scoped SQLite connection with foreign keys enabled."""
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE_PATH"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    """Create Milestone 1 tables. It is safe to call repeatedly."""
    schema_path = Path(__file__).with_name("schema.sql")
    connection = get_db()
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    connection.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
