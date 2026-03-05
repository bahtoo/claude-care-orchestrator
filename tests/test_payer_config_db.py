"""
Tests for multi-tenant PayerConfig DB model and seed script.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from care_orchestrator.database import Base
from care_orchestrator.models_db import PayerConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite session for PayerConfig tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def sample_payer(db_session):
    """Insert and return a sample PayerConfig."""
    config = PayerConfig(
        payer_id="commercial",
        display_name="Commercial Insurance",
        rules_json={"pa_required": True, "max_turnaround_hours": 72},
        active=True,
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


class TestPayerConfigCRUD:
    async def test_create_payer_config(self, db_session):
        config = PayerConfig(
            payer_id="medicare",
            display_name="Medicare",
            rules_json={"pa_required": False},
            active=True,
        )
        db_session.add(config)
        await db_session.commit()
        assert config.id is not None
        assert config.created_at is not None

    async def test_read_by_payer_id(self, db_session, sample_payer):
        stmt = select(PayerConfig).where(PayerConfig.payer_id == "commercial")
        result = await db_session.execute(stmt)
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.display_name == "Commercial Insurance"

    async def test_unique_payer_id_constraint(self, db_session, sample_payer):
        from sqlalchemy.exc import IntegrityError

        dup = PayerConfig(
            payer_id="commercial",  # duplicate
            display_name="Duplicate",
            rules_json={},
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_rules_json_round_trip(self, db_session, sample_payer):
        stmt = select(PayerConfig).where(PayerConfig.payer_id == "commercial")
        result = await db_session.execute(stmt)
        row = result.scalar_one()
        assert row.rules_json["pa_required"] is True
        assert row.rules_json["max_turnaround_hours"] == 72

    async def test_active_defaults_true(self, db_session):
        config = PayerConfig(payer_id="aetna", rules_json={})
        db_session.add(config)
        await db_session.commit()
        assert config.active is True

    async def test_filter_active_only(self, db_session):
        for payer_id, active in [("payer-a", True), ("payer-b", False), ("payer-c", True)]:
            db_session.add(PayerConfig(payer_id=payer_id, rules_json={}, active=active))
        await db_session.commit()

        stmt = select(PayerConfig).where(PayerConfig.active.is_(True))
        result = await db_session.execute(stmt)
        active_rows = result.scalars().all()
        assert len(active_rows) == 2

    async def test_update_rules_json(self, db_session, sample_payer):
        sample_payer.rules_json = {"pa_required": False, "max_turnaround_hours": 48}
        await db_session.commit()

        stmt = select(PayerConfig).where(PayerConfig.payer_id == "commercial")
        result = await db_session.execute(stmt)
        row = result.scalar_one()
        assert row.rules_json["max_turnaround_hours"] == 48

    async def test_deactivate_payer(self, db_session, sample_payer):
        sample_payer.active = False
        await db_session.commit()

        stmt = select(PayerConfig).where(PayerConfig.payer_id == "commercial")
        result = await db_session.execute(stmt)
        row = result.scalar_one()
        assert row.active is False


# ---------------------------------------------------------------------------
# Seed script tests
# ---------------------------------------------------------------------------


class TestPayerConfigSeed:
    async def test_seed_loads_json_files(self, tmp_path, db_session):
        """Seed script should create PayerConfig rows from JSON files."""

        from care_orchestrator.seeds.load_payer_configs import seed_payer_configs

        # Create test policy files
        policies_dir = tmp_path / "policies"
        policies_dir.mkdir()
        (policies_dir / "commercial.json").write_text(
            json.dumps({"pa_required": True, "max_hours": 72})
        )
        (policies_dir / "medicare.json").write_text(json.dumps({"pa_required": False}))

        # Patch the session to use our test session
        from unittest.mock import AsyncMock, patch

        # Run seed with a patched AsyncSessionLocal
        with patch(
            "care_orchestrator.seeds.load_payer_configs.create_tables",
            new_callable=AsyncMock,
        ):
            with patch("care_orchestrator.seeds.load_payer_configs.AsyncSessionLocal") as mock_sm:
                # Context manager that returns our db_session
                mock_sm.return_value.__aenter__ = AsyncMock(return_value=db_session)
                mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)

                count = await seed_payer_configs(policies_dir=policies_dir)

        assert count == 2

    async def test_seed_skips_invalid_json(self, tmp_path):
        """Seed script should skip files with invalid JSON gracefully."""
        from unittest.mock import AsyncMock, patch

        from care_orchestrator.seeds.load_payer_configs import seed_payer_configs

        policies_dir = tmp_path / "bad_policies"
        policies_dir.mkdir()
        (policies_dir / "broken.json").write_text("NOT JSON {{{")

        with patch(
            "care_orchestrator.seeds.load_payer_configs.create_tables",
            new_callable=AsyncMock,
        ):
            with patch("care_orchestrator.seeds.load_payer_configs.AsyncSessionLocal") as mock_sm:
                mock_session = AsyncMock()
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
                )
                mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)

                count = await seed_payer_configs(policies_dir=policies_dir)

        assert count == 0

    async def test_seed_empty_directory(self, tmp_path):
        """Seed returns 0 when no JSON files present."""
        from unittest.mock import AsyncMock, patch

        from care_orchestrator.seeds.load_payer_configs import seed_payer_configs

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch(
            "care_orchestrator.seeds.load_payer_configs.create_tables",
            new_callable=AsyncMock,
        ):
            count = await seed_payer_configs(policies_dir=empty_dir)

        assert count == 0


# Fix: make MagicMock importable in this test module
from unittest.mock import MagicMock  # noqa: E402
