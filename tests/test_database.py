"""
Tests for the SQLAlchemy async database layer.

Uses an in-memory SQLite database (aiosqlite) — no external services needed.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from care_orchestrator.database import Base
from care_orchestrator.models_db import PARecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Provide an in-memory SQLite async session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def sample_record(db_session):
    """Insert and return a sample PARecord."""
    record = PARecord(
        pa_number="PA-TEST-001",
        patient_id="patient-abc",
        status="approved",
        cpt_codes=["73221"],
        icd10_codes=["M23.5"],
        turnaround_minutes=4.5,
        result_json={"success": True, "summary": "Approved", "stages_completed": 4},
        summary="Approved after review",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


# ---------------------------------------------------------------------------
# PARecord CRUD
# ---------------------------------------------------------------------------


class TestPARecordCreate:
    @pytest.mark.asyncio
    async def test_create_record(self, db_session):
        record = PARecord(
            pa_number="PA-CREATE-001",
            patient_id="p1",
            status="pending",
            cpt_codes=["99213"],
            icd10_codes=["E11.9"],
            turnaround_minutes=2.1,
            result_json={},
            summary="",
        )
        db_session.add(record)
        await db_session.commit()
        assert record.id is not None

    @pytest.mark.asyncio
    async def test_pa_number_is_unique(self, db_session, sample_record):
        from sqlalchemy.exc import IntegrityError

        duplicate = PARecord(
            pa_number="PA-TEST-001",  # same as sample_record
            patient_id="p2",
            status="denied",
            cpt_codes=[],
            icd10_codes=[],
            turnaround_minutes=1.0,
            result_json={},
            summary="",
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_record_defaults(self, db_session):
        record = PARecord(pa_number="PA-DEFAULTS-001")
        db_session.add(record)
        await db_session.commit()
        assert record.status == "pending"
        assert record.cpt_codes == []
        assert record.icd10_codes == []
        assert record.turnaround_minutes == 0.0
        assert record.created_at is not None


class TestPARecordQuery:
    @pytest.mark.asyncio
    async def test_query_by_pa_number(self, db_session, sample_record):
        from sqlalchemy import select

        stmt = select(PARecord).where(PARecord.pa_number == "PA-TEST-001")
        result = await db_session.execute(stmt)
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.status == "approved"
        assert row.patient_id == "patient-abc"

    @pytest.mark.asyncio
    async def test_query_by_patient_id(self, db_session, sample_record):
        from sqlalchemy import select

        stmt = select(PARecord).where(PARecord.patient_id == "patient-abc")
        result = await db_session.execute(stmt)
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].pa_number == "PA-TEST-001"

    @pytest.mark.asyncio
    async def test_query_missing_returns_none(self, db_session):
        from sqlalchemy import select

        stmt = select(PARecord).where(PARecord.pa_number == "PA-NONEXISTENT")
        result = await db_session.execute(stmt)
        row = result.scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_json_fields_round_trip(self, db_session, sample_record):
        from sqlalchemy import select

        stmt = select(PARecord).where(PARecord.pa_number == "PA-TEST-001")
        result = await db_session.execute(stmt)
        row = result.scalar_one()
        assert row.cpt_codes == ["73221"]
        assert row.icd10_codes == ["M23.5"]
        assert row.result_json["success"] is True

    @pytest.mark.asyncio
    async def test_count_all_records(self, db_session, sample_record):
        from sqlalchemy import func, select

        total = (await db_session.execute(select(func.count()).select_from(PARecord))).scalar_one()
        assert total == 1

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db_session):
        from sqlalchemy import select

        for i, status in enumerate(["approved", "denied", "approved"]):
            db_session.add(
                PARecord(
                    pa_number=f"PA-STATUS-{i:03d}",
                    status=status,
                    cpt_codes=[],
                    icd10_codes=[],
                    result_json={},
                )
            )
        await db_session.commit()

        stmt = select(PARecord).where(PARecord.status == "approved")
        result = await db_session.execute(stmt)
        rows = result.scalars().all()
        assert len(rows) == 2


class TestCreateTables:
    @pytest.mark.asyncio
    async def test_create_tables_idempotent(self):
        """create_tables() should run twice without error."""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # second call — idempotent
        await engine.dispose()
