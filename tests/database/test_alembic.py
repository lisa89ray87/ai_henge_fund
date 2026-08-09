"""Tests for the Alembic infrastructure configuration."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import sqlalchemy
from alembic.config import Config
from pydantic import SecretStr

from ai_henge_fund.database.base import Base

PROJECT_ROOT = Path(__file__).parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
ALEMBIC_ENV_PATH = PROJECT_ROOT / "alembic" / "env.py"


def load_alembic_environment(module_name: str = "test_alembic_environment") -> ModuleType:
    """Load the environment without using Alembic's execution module name."""
    spec = importlib.util.spec_from_file_location(module_name, ALEMBIC_ENV_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Alembic environment configuration.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_alembic_configuration_loads_without_a_database_url() -> None:
    config = Config(str(ALEMBIC_INI_PATH))

    assert config.get_main_option("script_location") == "alembic"
    assert config.get_main_option("sqlalchemy.url") is None


def test_application_database_url_is_used_without_persisting_it(
    monkeypatch,
) -> None:
    environment = load_alembic_environment()
    database_url = "postgresql+psycopg://user:password@example.neon.tech/database?sslmode=require"
    monkeypatch.setattr(
        environment,
        "get_settings",
        lambda: SimpleNamespace(database_url=SecretStr(database_url)),
    )

    assert environment.get_database_url() == database_url
    assert "sqlalchemy.url" not in Config(str(ALEMBIC_INI_PATH)).get_section("alembic")


def test_target_metadata_is_the_project_base_metadata() -> None:
    environment = load_alembic_environment()

    assert environment.target_metadata is Base.metadata


def test_importing_environment_does_not_create_an_engine(monkeypatch) -> None:
    engine_factory = MagicMock()
    monkeypatch.setattr(sqlalchemy, "engine_from_config", engine_factory)

    load_alembic_environment("test_alembic_environment_without_engine")

    engine_factory.assert_not_called()


def test_alembic_configuration_does_not_log_or_store_secrets(caplog, monkeypatch) -> None:
    environment = load_alembic_environment()
    database_url = "postgresql+psycopg://user:password@example.neon.tech/database?sslmode=require"
    monkeypatch.setattr(
        environment,
        "get_settings",
        lambda: SimpleNamespace(database_url=SecretStr(database_url)),
    )

    environment.get_database_url()

    assert database_url not in caplog.text
    assert "password" not in ALEMBIC_INI_PATH.read_text(encoding="utf-8")
