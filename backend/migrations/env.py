"""
Alembic migration environment.
Configured for sync PostgreSQL (Alembic doesn't support asyncpg directly).

The key line is `import models` — this registers the Job model with Base.metadata
so that `alembic revision --autogenerate` can detect table definitions.
"""

import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import pool, create_engine
from alembic import context

# Add backend directory to Python path so we can import our modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import Base (carries metadata) and models (registers tables with Base)
from database import Base
import models  # noqa: F401 — import triggers Job table registration

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is what Alembic uses to detect tables and generate migrations
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without connecting to the database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()