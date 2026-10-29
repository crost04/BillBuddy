"""Alembic environment: tells Alembic which database and which models to use."""

from alembic import context

from billbuddy.db import Base, import_models, make_engine

import_models()
target_metadata = Base.metadata


def run(connection) -> None:
    # render_as_batch: SQLite can only change tables by recreating them;
    # batch mode does that automatically
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


# The app passes its own connection (see init_db); the command line uses DATABASE_URL
connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    with make_engine().begin() as connection:
        run(connection)
