"""
Separate database engine/session for the provenance ("our own image
database") layer.

Deliberately kept independent from app/database.py's SQLite
`investigations` DB:
- pgvector requires Postgres, the existing investigations DB is SQLite by
  default and we don't want to force a Postgres dependency onto the
  existing, working investigation pipeline just to add this layer.
- The provenance store is meant to persist and grow forever, independent
  of any single investigation -- it's a shared index, not a per-run table.

PROVENANCE_DATABASE_URL must point at a Postgres instance with the
`vector` extension available (the `pgvector/pgvector` docker image ships
this). See docker-compose.yml's `provdb` service.
"""
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

logger = logging.getLogger("provenance_db")

ProvenanceBase = declarative_base()

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        if not settings.PROVENANCE_DATABASE_URL:
            raise RuntimeError(
                "PROVENANCE_DATABASE_URL is not set. Set it in .env, e.g. "
                "postgresql+psycopg2://provenance:provenance@localhost:5433/provenance "
                "(see docker-compose.yml's provdb service)."
            )
        _engine = create_engine(settings.PROVENANCE_DATABASE_URL, pool_pre_ping=True)
    return _engine


def get_provenance_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_provenance_db():
    """Creates the `vector` extension (if missing) and all provenance
    tables. Safe to call repeatedly -- CREATE EXTENSION IF NOT EXISTS and
    create_all() are both idempotent. Like the existing SQLite database.py,
    this project has no Alembic; for pure additive column growth later,
    follow the same pattern that file documents (or introduce Alembic if
    this layer needs real migrations before then)."""
    from app.models import provenance  # noqa: F401  registers models on ProvenanceBase

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    ProvenanceBase.metadata.create_all(bind=engine)
    logger.info("Provenance database ready (%s)", engine.url.database)
