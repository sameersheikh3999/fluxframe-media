"""SQLAlchemy declarative base and shared column types.

Two decisions in here are worth more than they look.

**1. The naming convention.** Without it, Alembic autogenerate produces
constraints with database-assigned names, and a downgrade cannot reliably drop
what it does not know the name of. Setting it before the first migration costs
nothing; retrofitting it later means rewriting history. This is the single
cheapest thing you can do on day one of a SQLAlchemy project.

**2. Portable column types with PostgreSQL variants.** Production runs
PostgreSQL and uses JSONB. The test suite runs SQLite, so the whole suite works
on a laptop and in CI with no database server. `JSON().with_variant(JSONB,
"postgresql")` gives us both from one model definition — SQLite stores JSON as
text, PostgreSQL stores real JSONB and can index it.

This is a deliberate, narrow use of SQLite: tests only, never production, and no
SQLite-specific SQL anywhere. See docs/testing.md.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import JSON, TypeEngine

#: Deterministic constraint names, so migrations can always drop what they made.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: JSONB on PostgreSQL (indexable, binary), plain JSON elsewhere.
JsonDict: TypeEngine[Any] = JSON().with_variant(JSONB(), "postgresql")

#: Every timestamp in this system is timezone-aware UTC. Naive datetimes in a
#: database are a category of bug that is tedious to find and trivial to avoid.
TimestampTz = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {  # noqa: RUF012
        datetime: TimestampTz,
        dict[str, Any]: JsonDict,
    }
