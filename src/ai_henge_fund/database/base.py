"""Declarative base and shared persistence helpers."""

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for persistence models."""


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for Python-side column defaults."""
    return datetime.now(UTC)
