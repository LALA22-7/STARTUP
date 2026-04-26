"""
Property-based test: Encounter list is bounded and ordered.

Property 5: For any patient, `GET /api/patients/{id}/encounters` SHALL return
at most 10 records, and the records SHALL be sorted by `created_at` in
descending order (most recent first).

Validates: Requirements 4.2, 5.6
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Minimal SQLite-compatible ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "Patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class Encounter(Base):
    __tablename__ = "Encounters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("Patients.id", ondelete="CASCADE"), nullable=False
    )
    record: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


# ---------------------------------------------------------------------------
# Query function — mirrors GET /api/patients/{patient_id}/encounters
# ---------------------------------------------------------------------------

ENCOUNTER_LIMIT = 10


async def query_patient_encounters(
    session_factory,
    patient_id: int,
) -> List[dict]:
    """
    Execute the same encounter query as GET /api/patients/{id}/encounters.

    Returns at most 10 encounters sorted by created_at descending.
    """
    async with session_factory() as session:
        stmt = (
            select(Encounter)
            .where(Encounter.patient_id == patient_id)
            .order_by(Encounter.created_at.desc())
            .limit(ENCOUNTER_LIMIT)
        )
        result = await session.execute(stmt)
        encounters = result.scalars().all()

    return [
        {
            "id": e.id,
            "patient_id": e.patient_id,
            "record": e.record,
            "created_at": e.created_at,
        }
        for e in encounters
    ]


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine from a synchronous context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate a list of 0–25 encounter counts (more than the 10-item limit)
encounter_count_strategy = st.integers(min_value=0, max_value=25)


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(num_encounters=encounter_count_strategy)
def test_encounter_list_bounded_and_ordered(num_encounters: int):
    """
    **Validates: Requirements 4.2, 5.6**

    Property 5: Encounter list is bounded and ordered.

    For any number of encounters seeded for a patient:
    - The returned list SHALL contain at most 10 items.
    - The returned list SHALL be sorted by created_at in descending order
      (most recent first).
    - When num_encounters <= 10, all encounters SHALL be returned.
    - When num_encounters > 10, exactly 10 encounters SHALL be returned,
      and they SHALL be the 10 most recent ones.
    """
    run_async(_run_encounter_property(num_encounters))


async def _run_encounter_property(num_encounters: int) -> None:
    """
    Async implementation of the encounter ordering and bound property test.

    Seeds an in-memory SQLite database with `num_encounters` encounters for
    a single patient, each with a distinct created_at timestamp spaced 1 hour
    apart. Runs the query and asserts the bound and ordering properties.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Base timestamp: encounters are spaced 1 hour apart
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        async with session_factory() as session:
            async with session.begin():
                patient = Patient(
                    full_name="Test Patient",
                    email="test@example.com",
                    phone="9000000000",
                )
                session.add(patient)
                await session.flush()

                # Seed encounters with ascending timestamps (oldest first)
                for i in range(num_encounters):
                    encounter = Encounter(
                        patient_id=patient.id,
                        record={"index": i, "note": f"encounter {i}"},
                        created_at=base_time + timedelta(hours=i),
                    )
                    session.add(encounter)

                patient_id = patient.id

        # Run the query
        results = await query_patient_encounters(session_factory, patient_id)

        # --- Bound assertion: at most 10 results ---
        assert len(results) <= ENCOUNTER_LIMIT, (
            f"Expected at most {ENCOUNTER_LIMIT} encounters, "
            f"got {len(results)} (num_encounters={num_encounters})"
        )

        # --- Exact count assertion ---
        expected_count = min(num_encounters, ENCOUNTER_LIMIT)
        assert len(results) == expected_count, (
            f"Expected exactly {expected_count} encounters, "
            f"got {len(results)} (num_encounters={num_encounters})"
        )

        # --- Ordering assertion: descending by created_at ---
        for i in range(len(results) - 1):
            assert results[i]["created_at"] >= results[i + 1]["created_at"], (
                f"Encounters not sorted descending at index {i}: "
                f"{results[i]['created_at']} < {results[i + 1]['created_at']}"
            )

        # --- Recency assertion: when more than 10 exist, the 10 most recent are returned ---
        if num_encounters > ENCOUNTER_LIMIT:
            # The most recent encounter has index (num_encounters - 1)
            # The 10th most recent has index (num_encounters - 10)
            most_recent_expected = base_time + timedelta(hours=num_encounters - 1)
            oldest_expected = base_time + timedelta(hours=num_encounters - ENCOUNTER_LIMIT)

            # SQLite may strip timezone info when reading back DateTime(timezone=True)
            # columns; compare as naive UTC datetimes to avoid false failures.
            def _naive(dt: datetime) -> datetime:
                return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

            assert _naive(results[0]["created_at"]) == _naive(most_recent_expected), (
                f"First result should be the most recent encounter "
                f"(created_at={most_recent_expected}), "
                f"got {results[0]['created_at']}"
            )
            assert _naive(results[-1]["created_at"]) == _naive(oldest_expected), (
                f"Last result should be the {ENCOUNTER_LIMIT}th most recent encounter "
                f"(created_at={oldest_expected}), "
                f"got {results[-1]['created_at']}"
            )

    finally:
        await engine.dispose()


@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(num_encounters=st.integers(min_value=0, max_value=10))
def test_encounter_list_returns_all_when_under_limit(num_encounters: int):
    """
    **Validates: Requirements 4.2, 5.6**

    When the total number of encounters is at or below the 10-item limit,
    ALL encounters SHALL be returned.
    """
    run_async(_run_under_limit_property(num_encounters))


async def _run_under_limit_property(num_encounters: int) -> None:
    """Verify all encounters are returned when count <= ENCOUNTER_LIMIT."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        base_time = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)

        async with session_factory() as session:
            async with session.begin():
                patient = Patient(
                    full_name="Test Patient",
                    email="test2@example.com",
                    phone="9111111111",
                )
                session.add(patient)
                await session.flush()

                for i in range(num_encounters):
                    session.add(Encounter(
                        patient_id=patient.id,
                        record={"i": i},
                        created_at=base_time + timedelta(hours=i),
                    ))

                patient_id = patient.id

        results = await query_patient_encounters(session_factory, patient_id)

        assert len(results) == num_encounters, (
            f"Expected all {num_encounters} encounters to be returned "
            f"(under limit), got {len(results)}"
        )

    finally:
        await engine.dispose()


@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(num_encounters=st.integers(min_value=11, max_value=25))
def test_encounter_list_capped_at_ten_when_over_limit(num_encounters: int):
    """
    **Validates: Requirements 4.2, 5.6**

    When the total number of encounters exceeds 10, exactly 10 SHALL be
    returned, and they SHALL be the 10 most recent.
    """
    run_async(_run_over_limit_property(num_encounters))


async def _run_over_limit_property(num_encounters: int) -> None:
    """Verify exactly 10 most recent encounters are returned when count > 10."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        base_time = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)

        async with session_factory() as session:
            async with session.begin():
                patient = Patient(
                    full_name="Test Patient",
                    email="test3@example.com",
                    phone="9222222222",
                )
                session.add(patient)
                await session.flush()

                for i in range(num_encounters):
                    session.add(Encounter(
                        patient_id=patient.id,
                        record={"i": i},
                        created_at=base_time + timedelta(hours=i),
                    ))

                patient_id = patient.id

        results = await query_patient_encounters(session_factory, patient_id)

        assert len(results) == ENCOUNTER_LIMIT, (
            f"Expected exactly {ENCOUNTER_LIMIT} encounters when {num_encounters} exist, "
            f"got {len(results)}"
        )

        # The most recent encounter should be first
        # SQLite may strip timezone info; compare as naive UTC datetimes.
        def _naive(dt: datetime) -> datetime:
            return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

        most_recent = base_time + timedelta(hours=num_encounters - 1)
        assert _naive(results[0]["created_at"]) == _naive(most_recent), (
            f"First result should be most recent (created_at={most_recent}), "
            f"got {results[0]['created_at']}"
        )

    finally:
        await engine.dispose()
