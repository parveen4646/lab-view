import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import Config

logger = logging.getLogger(__name__)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        # Bare "postgresql://" lets SQLAlchemy pick a driver, and it resolves to
        # the psycopg (v3) dialect if that package is merely importable — we
        # install psycopg2-binary, so pin the driver explicitly to match.
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]

    # psycopg2's bundled libpq doesn't recognize "channel_binding" (a SCRAM
    # channel-binding parameter Neon's connection strings include by
    # default) and fails every connection with "invalid channel_binding
    # value" — strip it. sslmode=require already enforces an encrypted
    # connection on its own.
    parts = urlsplit(url)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    filtered_pairs = [(k, v) for k, v in query_pairs if k != "channel_binding"]
    if len(filtered_pairs) != len(query_pairs):
        url = urlunsplit(parts._replace(query=urlencode(filtered_pairs)))

    return url


_database_url = _normalize_database_url(Config.DATABASE_URL)

engine = create_engine(
    _database_url,
    connect_args={"check_same_thread": False} if _database_url.startswith("sqlite") else {},
    pool_pre_ping=True,  # Neon/serverless Postgres drops idle connections
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from db import models  # noqa: F401 — imports trigger table registration
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """
    create_all() only creates missing tables, not missing columns on tables
    that already exist. This adds any columns a model gained since the table
    was first created — additive only, safe to run on every startup.
    """
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            col_type = column.type.compile(dialect=engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"))
            logger.info("Added column %s.%s", table.name, column.name)
