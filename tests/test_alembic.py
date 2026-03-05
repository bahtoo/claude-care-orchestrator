"""
Tests for Alembic migration round-trips.

Runs upgrade head → downgrade base → upgrade head on an in-memory
SQLite database, verifying the migration scripts are valid without
requiring any external database server.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config


def _alembic_cfg(db_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    # Silence alembic log output during tests
    import logging

    logging.getLogger("alembic").setLevel(logging.ERROR)
    return cfg


class TestAlembicMigrations:
    def test_upgrade_to_head(self, tmp_path):
        """Upgrade from empty DB to head creates all tables."""
        db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
        cfg = _alembic_cfg(db_url)
        command.upgrade(cfg, "head")  # should not raise

    def test_downgrade_to_base(self, tmp_path):
        """Full upgrade → full downgrade leaves DB clean."""
        db_url = f"sqlite+aiosqlite:///{tmp_path / 'roundtrip.db'}"
        cfg = _alembic_cfg(db_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")  # should not raise

    def test_upgrade_downgrade_upgrade_roundtrip(self, tmp_path):
        """Double upgrade round-trip: idempotency check."""
        db_url = f"sqlite+aiosqlite:///{tmp_path / 'idempotent.db'}"
        cfg = _alembic_cfg(db_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")  # second upgrade — no error

    def test_upgrade_creates_pa_records(self, tmp_path):
        """After upgrade head, pa_records table must exist."""
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_path = tmp_path / "tables.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        cfg = _alembic_cfg(db_url)
        command.upgrade(cfg, "head")

        async def check_tables():
            engine = create_async_engine(db_url)
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
                tables = {row[0] for row in result}
            await engine.dispose()
            return tables

        tables = asyncio.run(check_tables())
        assert "pa_records" in tables
        assert "payer_configs" in tables

    def test_downgrade_removes_tables(self, tmp_path):
        """After downgrade base, both tables must be gone."""
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_path = tmp_path / "down.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        cfg = _alembic_cfg(db_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        async def check_tables():
            engine = create_async_engine(db_url)
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
                tables = {row[0] for row in result}
            await engine.dispose()
            return tables

        tables = asyncio.run(check_tables())
        assert "pa_records" not in tables
        assert "payer_configs" not in tables

    def test_migration_revision_history(self, tmp_path):
        """Both migration revisions must be present in version history."""
        db_url = f"sqlite+aiosqlite:///{tmp_path / 'hist.db'}"
        cfg = _alembic_cfg(db_url)
        # Verify scripts can be loaded without error
        from alembic.script import ScriptDirectory

        scripts = ScriptDirectory.from_config(cfg)
        revisions = [s.revision for s in scripts.walk_revisions()]
        assert "0001" in revisions
        assert "0002" in revisions
