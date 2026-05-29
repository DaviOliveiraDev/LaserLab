from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.config import DATABASE_URL

# Check if SQLite and apply thread workarounds
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL, connect_args=connect_args
)

def run_migrations():
    """Engine-agnostic auto-migration helper to add missing columns to existing tables."""
    inspector = inspect(engine)
    if "jobs" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("jobs")]
        if "template_id" not in columns:
            print("Auto-migration: Adding template_id column to jobs table...")
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN template_id INTEGER"))
                print("Auto-migration completed successfully.")
            except Exception as e:
                print(f"Auto-migration failed: {e}")

# Run migrations automatically when database module is imported
run_migrations()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
