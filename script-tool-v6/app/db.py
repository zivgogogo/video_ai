from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def _migrate(eng):
    """Add missing columns to existing tables (dev-only lightweight migration)."""
    inspector = inspect(eng)
    with eng.connect() as conn:
        if "pipeline_runs" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("pipeline_runs")}
            if "paused" not in cols:
                conn.execute(text("ALTER TABLE pipeline_runs ADD COLUMN paused INTEGER DEFAULT 0"))
            if "paused_at_stage" not in cols:
                conn.execute(text("ALTER TABLE pipeline_runs ADD COLUMN paused_at_stage INTEGER"))
            conn.commit()
