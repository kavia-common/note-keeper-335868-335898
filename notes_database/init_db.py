#!/usr/bin/env python3
"""Initialize and migrate SQLite database for notes_database.

This script is designed to be idempotent: it can be run multiple times safely.
It creates the notes schema (notes + optional tags) and applies incremental
migrations tracked in a schema_migrations table.

Schema highlights:
- notes: main entity with created_at / updated_at timestamps
- tags: optional labels
- note_tags: many-to-many join table for tag filtering
- notes_fts: FTS5 virtual table for fast search over title/content

Indexes are created to support:
- listing notes by updated_at (descending)
- filtering by tag
- fast lookups in join tables
- FTS search

Side effects:
- Creates/updates myapp.db
- Overwrites db_connection.txt with current connection info
- Overwrites db_visualizer/sqlite.env with absolute SQLITE_DB path
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

DB_NAME = "myapp.db"
DB_USER = "kaviasqlite"  # Not used for SQLite, but kept for consistency
DB_PASSWORD = "kaviadefaultpassword"  # Not used for SQLite, but kept for consistency
DB_PORT = "5000"  # Not used for SQLite, but kept for consistency


def _utcnow_iso() -> str:
    """Return current UTC time in ISO-8601 format without timezone suffix.

    SQLite stores timestamps as TEXT in this project to keep things simple and portable.
    """
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat(sep=" ")


@dataclass(frozen=True)
class Migration:
    """Represents a single schema migration."""
    version: int
    name: str
    statements: Tuple[str, ...]


# PUBLIC_INTERFACE
def init_and_migrate_db(db_path: str = DB_NAME) -> None:
    """Initialize and migrate the SQLite database to the latest schema.

    Contract:
      Inputs:
        - db_path: path to the SQLite database file (default: myapp.db)
      Behavior:
        - Ensures the database file exists
        - Enables foreign keys
        - Creates schema_migrations bookkeeping table
        - Applies any pending migrations in ascending version order
        - Creates/refreshes triggers that maintain updated_at and FTS sync
      Errors:
        - Raises sqlite3.Error (wrapped with context) on any DB failure
      Side effects:
        - Creates/updates schema objects in the SQLite database file
    """
    print("Starting SQLite setup...")

    db_exists = os.path.exists(db_path)
    if db_exists:
        print(f"SQLite database already exists at {db_path}")
    else:
        print("Creating new SQLite database...")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Critical for referential integrity
        cursor.execute("PRAGMA foreign_keys = ON")

        _ensure_migrations_table(cursor)
        applied = _get_applied_migration_versions(cursor)

        migrations = _get_migrations()
        pending = [m for m in migrations if m.version not in applied]

        if not pending:
            print("No pending migrations.")
        else:
            print(f"Applying {len(pending)} migration(s)...")

        for m in pending:
            _apply_migration(conn, cursor, m)

        # Ensure “always present” schema helpers (can evolve without version bump)
        _ensure_triggers(cursor)
        conn.commit()

        # Quick health check
        cursor.execute("SELECT 1")
        print("Database is accessible and working.")

        # Statistics for the operator
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM notes")
        notes_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tags")
        tags_count = cursor.fetchone()[0]

        print("\nSQLite setup complete!")
        print(f"Database: {db_path}")
        print(f"Location: {os.getcwd()}/{db_path}")
        print("")
        print("Database statistics:")
        print(f"  Tables: {table_count}")
        print(f"  Notes: {notes_count}")
        print(f"  Tags: {tags_count}")

    except sqlite3.Error as e:
        raise sqlite3.Error(f"init_and_migrate_db failed for {db_path}: {e}") from e
    finally:
        try:
            conn.close()
        except Exception:
            pass

    _write_connection_info(db_path=db_path)
    _write_visualizer_env(db_path=db_path)

    # If sqlite3 CLI is available, show how to use it
    try:
        import subprocess

        result = subprocess.run(["which", "sqlite3"], capture_output=True, text=True)
        if result.returncode == 0:
            print("")
            print("SQLite CLI is available. You can also use:")
            print(f"  sqlite3 {db_path}")
    except Exception:
        pass

    print("\nScript completed successfully.")


def _ensure_migrations_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _get_applied_migration_versions(cursor: sqlite3.Cursor) -> set[int]:
    cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {int(r[0]) for r in cursor.fetchall()}


def _apply_migration(conn: sqlite3.Connection, cursor: sqlite3.Cursor, migration: Migration) -> None:
    """Apply a migration inside a transaction boundary.

    We insert the migration row only after all statements succeed.
    """
    print(f"-> Migration {migration.version}: {migration.name}")
    try:
        for stmt in migration.statements:
            cursor.execute(stmt)
        cursor.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?, ?, ?)",
            (migration.version, migration.name, _utcnow_iso()),
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise sqlite3.Error(
            f"Migration {migration.version} ({migration.name}) failed: {e}"
        ) from e


def _get_migrations() -> List[Migration]:
    """Return the full ordered migration list.

    Note: We keep migrations append-only. Do not edit old migrations in-place.
    """
    # Migration 1: Core notes + tags schema (+ indexes) and FTS search.
    # - notes.updated_at maintained via triggers
    # - note_tags enables tag filtering
    # - FTS enables fast search; triggers sync FTS with notes
    return [
        Migration(
            version=1,
            name="create notes/tags schema with indexes and FTS",
            statements=(
                # NOTES
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """,
                # TAGS
                """
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """,
                # JOIN TABLE
                """
                CREATE TABLE IF NOT EXISTS note_tags (
                    note_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (note_id, tag_id),
                    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
                """,
                # Indexes for listing/sorting and tag filtering
                "CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id)",
                "CREATE INDEX IF NOT EXISTS idx_note_tags_note_id ON note_tags(note_id)",
                # FTS5 virtual table for search (title + content)
                # content='notes' makes this an external content table (keeps storage minimal).
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
                USING fts5(
                    title,
                    content,
                    content='notes',
                    content_rowid='id',
                    tokenize='unicode61'
                )
                """,
                # Seed FTS index for existing rows (idempotent via REPLACE)
                """
                INSERT OR REPLACE INTO notes_fts(rowid, title, content)
                SELECT id, title, content FROM notes
                """,
            ),
        )
    ]


def _ensure_triggers(cursor: sqlite3.Cursor) -> None:
    """Ensure triggers exist to maintain updated_at and synchronize FTS.

    These are created outside the migration list so we can refine trigger logic
    without needing to bump schema version for minor correctness tweaks.
    """
    # updated_at maintenance
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_notes_set_updated_at
        AFTER UPDATE OF title, content ON notes
        FOR EACH ROW
        BEGIN
            UPDATE notes
            SET updated_at = datetime('now')
            WHERE id = NEW.id;
        END
        """
    )

    # FTS synchronization triggers (external content table pattern)
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_notes_fts_ai
        AFTER INSERT ON notes
        BEGIN
            INSERT INTO notes_fts(rowid, title, content)
            VALUES (NEW.id, NEW.title, NEW.content);
        END
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_notes_fts_ad
        AFTER DELETE ON notes
        BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content)
            VALUES ('delete', OLD.id, OLD.title, OLD.content);
        END
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_notes_fts_au
        AFTER UPDATE OF title, content ON notes
        BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content)
            VALUES ('delete', OLD.id, OLD.title, OLD.content);
            INSERT INTO notes_fts(rowid, title, content)
            VALUES (NEW.id, NEW.title, NEW.content);
        END
        """
    )


def _write_connection_info(db_path: str) -> None:
    """Write db_connection.txt with the current absolute connection details."""
    current_dir = os.getcwd()
    connection_string = f"sqlite:///{current_dir}/{db_path}"

    try:
        with open("db_connection.txt", "w", encoding="utf-8") as f:
            f.write("# SQLite connection methods:\n")
            f.write(f"# Python: sqlite3.connect('{db_path}')\n")
            f.write(f"# Connection string: {connection_string}\n")
            f.write(f"# File path: {current_dir}/{db_path}\n")
        print("Connection information saved to db_connection.txt")
    except Exception as e:
        print(f"Warning: Could not save connection info: {e}")


def _write_visualizer_env(db_path: str) -> None:
    """Write db_visualizer/sqlite.env used by the bundled DB viewer."""
    db_abs_path = os.path.abspath(db_path)

    if not os.path.exists("db_visualizer"):
        os.makedirs("db_visualizer", exist_ok=True)
        print("Created db_visualizer directory")

    try:
        with open("db_visualizer/sqlite.env", "w", encoding="utf-8") as f:
            f.write(f'export SQLITE_DB="{db_abs_path}"\n')
        print("Environment variables saved to db_visualizer/sqlite.env")
    except Exception as e:
        print(f"Warning: Could not save environment variables: {e}")


if __name__ == "__main__":
    init_and_migrate_db(DB_NAME)
