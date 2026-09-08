"""
Database engine/session setup + a minimal, dependency-free schema-upgrade
mechanism for SQLite.

This project does not use Alembic. `Base.metadata.create_all()` alone is
NOT sufficient for keeping an existing SQLite file's schema current: it
only creates tables that don't exist yet -- it never adds columns to a
table that is already present (see `_add_missing_columns` below for the
concrete failure mode this caused). `init_db()` therefore runs create_all()
followed by a lightweight additive column-migration pass so that both a
brand-new database file and an existing one (dev DB, stale test DB, etc.)
always end up with every column the current SQLAlchemy models define.
"""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

logger = logging.getLogger("database")

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """
    Additive SQLite schema migration.

    `create_all()` only issues `CREATE TABLE IF NOT EXISTS` -- for a table
    that already exists on disk (e.g. a dev DB or a stale test DB created
    by an older version of a model), it silently does nothing, even if the
    current model has grown new columns since that file was created. That
    mismatch is exactly what produced:

        sqlite3.OperationalError: table ai_detections has no column named
        detector_status

    when `AIDetection.detector_status` was added to the model but an
    existing `forensics.db` / `ai_detections` table on disk predated it.

    This walks every table SQLAlchemy knows about, compares its *actual*
    on-disk columns (via `inspect()`) against the columns the current model
    declares, and issues `ALTER TABLE ... ADD COLUMN ...` for anything
    missing. SQLite's `ADD COLUMN` is additive-only (no rename/drop/type
    change), which is exactly what's needed here and is always safe:
      - it never touches or drops existing columns/data, so all existing
        rows and their existing column values are preserved as-is;
      - new columns are added as nullable (existing rows simply read back
        as NULL/None for them -- e.g. an old AIDetection row's
        `detector_status` reads back as None, which app.services.report
        already treats as "NOT CONFIGURED"), since SQLite's ADD COLUMN
        cannot retroactively backfill a NOT NULL value for pre-existing
        rows and every column added after initial release here is
        declared nullable for exactly this reason.

    This intentionally does NOT attempt to handle column removal, type
    changes, or renames -- if this project's schema ever needs one of
    those, that's the point to introduce a real migration tool (Alembic).
    For pure additive column growth, this is the smallest mechanism that
    keeps `create_all()`'s "just works" ergonomics for a fresh DB while
    also fixing up an existing one.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            # Brand-new table -- create_all() already created it with the
            # full current schema, nothing to migrate.
            continue

        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue

            ddl_type = column.type.compile(dialect=engine.dialect)
            statement = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'
            logger.info("Migrating SQLite schema: %s", statement)
            with engine.begin() as conn:
                conn.execute(text(statement))


def init_db():
    from app.models import investigation  # noqa: F401  (ensure models are registered)
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _add_missing_columns()
