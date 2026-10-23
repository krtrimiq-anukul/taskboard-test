"""Applies migrations/versions to the database in DATABASE_URL."""
import logging

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

load_dotenv()  # backend/.env, for local runs only

import models  # noqa: E402,F401  (registers the tables)
from db import Base, database_url  # noqa: E402

# Shows "Running upgrade -> 0001" lines (in CloudWatch when the Deploy tab runs it).
logging.basicConfig(level=logging.WARNING, format="%(levelname)s [%(name)s] %(message)s")
logging.getLogger("alembic").setLevel(logging.INFO)
target_metadata = Base.metadata


def run_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
