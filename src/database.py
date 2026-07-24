"""Database connection and session management."""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base


def _build_database_url():
    """Build the DB connection URL.

    Prefers discrete DB_HOST/DB_USER/DB_PASSWORD/... env vars, built via
    SQLAlchemy's URL.create() which percent-encodes credentials automatically.
    This avoids breakage when a password contains characters like '@' or '/'
    that corrupt a hand-assembled "postgresql://user:pass@host/db" string
    (e.g. Supabase passwords are randomly generated and often contain '@').
    Falls back to a single DATABASE_URL string, then to local SQLite.
    """
    host = os.getenv("DB_HOST")
    if host:
        return URL.create(
            "postgresql+psycopg2",
            username=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD"),
            host=host,
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "postgres"),
        )
    return os.getenv(
        "DATABASE_URL",
        "sqlite:///drift_monitor.db"  # Local SQLite database for development
    )


DATABASE_URL = _build_database_url()
_is_postgres = "postgresql" in str(DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True if _is_postgres else False,
    connect_args={"check_same_thread": False} if not _is_postgres else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
