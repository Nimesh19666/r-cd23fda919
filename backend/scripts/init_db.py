"""Create the database tables. Usage (from backend/, venv active):

python scripts/init_db.py
"""

from sqlalchemy import text

from app.db import apply_schema, get_engine


def main() -> None:
    engine = get_engine()
    apply_schema(engine)
    query = text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    )
    with engine.connect() as conn:
        tables = conn.execute(query).scalars().all()
    print("Tables in database:", tables)


if __name__ == "__main__":
    main()
