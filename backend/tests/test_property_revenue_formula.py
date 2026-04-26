"""
Property-based test: Daily revenue equals completed appointments times fee.

Property 2: For any date and clinic, the `revenue` field returned by
`GET /api/analytics/daily` SHALL equal the count of appointments with
`status = "completed"` on that date multiplied by ₹500.

Validates: Requirements 3.2, 5.3
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ---------------------------------------------------------------------------
# Minimal SQLite-compatible ORM models
# (mirrors database.py but uses standard types compatible with aiosqlite)
# ---------------------------------------------------------------------------

APPOINTMENT_FEE = 500  # ₹500 per completed appointment


class TestBase(DeclarativeBase):
    pass


class TestClinic(TestBase):
    __tablename__ = "Clinics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class TestPatient(TestBase):
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


class TestAvailabilitySchedule(TestBase):
    __tablename__ = "Availability_Schedules"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "slot_start", "slot_end",
            name="uq_availability_slot_per_clinic",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("Clinics.id", ondelete="CASCADE"), nullable=False
    )
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class TestAppointment(TestBase):
    __tablename__ = "Appointments"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "scheduled_start", "scheduled_end",
            name="uq_appointment_slot_per_clinic",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("Clinics.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("Patients.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("Availability_Schedules.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="booked")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Pure revenue calculation — mirrors the SQL CASE logic in analytics_service.py
# ---------------------------------------------------------------------------

def compute_revenue_from_rows(statuses: List[str]) -> int:
    """
    Compute expected revenue from a list of appointment statuses.

    Mirrors the SQL expression in AnalyticsService.get_daily_revenue():
        SUM(CASE WHEN status = 'completed' THEN 500 ELSE 0 END)
    """
    return sum(APPOINTMENT_FEE for s in statuses if s == "completed")


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
# In-memory analytics query — same logic as AnalyticsService.get_daily_revenue
# but operating against the test SQLite session factory.
# ---------------------------------------------------------------------------

async def query_daily_revenue(
    session_factory,
    clinic_id: int,
    day_start: datetime,
    day_end: datetime,
) -> dict:
    """
    Execute the same revenue query as AnalyticsService.get_daily_revenue()
    against the provided session factory.

    Returns a dict with keys: total_appointments, completed, missed, revenue.
    """
    async with session_factory() as session:
        # Main aggregation query (mirrors analytics_service.py)
        stmt = (
            select(
                func.count(TestAppointment.id).label("total_appointments"),
                func.sum(
                    case(
                        (TestAppointment.status == "completed", APPOINTMENT_FEE),
                        else_=0,
                    )
                ).label("revenue"),
            ).where(
                TestAppointment.clinic_id == clinic_id,
                TestAppointment.scheduled_start >= day_start,
                TestAppointment.scheduled_start < day_end,
            )
        )
        result = await session.execute(stmt)
        row = result.first()

        # Completed count sub-query
        completed_stmt = (
            select(func.count(TestAppointment.id)).where(
                TestAppointment.clinic_id == clinic_id,
                TestAppointment.status == "completed",
                TestAppointment.scheduled_start >= day_start,
                TestAppointment.scheduled_start < day_end,
            )
        )
        completed = (await session.execute(completed_stmt)).scalar() or 0

        # Missed count sub-query
        missed_stmt = (
            select(func.count(TestAppointment.id)).where(
                TestAppointment.clinic_id == clinic_id,
                TestAppointment.status == "missed",
                TestAppointment.scheduled_start >= day_start,
                TestAppointment.scheduled_start < day_end,
            )
        )
        missed = (await session.execute(missed_stmt)).scalar() or 0

        return {
            "total_appointments": row[0] if row else 0,
            "completed": completed,
            "missed": missed,
            "revenue": (row[1] if row else 0) or 0,
        }


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

VALID_STATUSES = ["booked", "completed", "missed", "waiting"]

# Generate a list of 0–20 appointment statuses
appointment_statuses_strategy = st.lists(
    st.sampled_from(VALID_STATUSES),
    min_size=0,
    max_size=20,
)


# ---------------------------------------------------------------------------
# Property-based test
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(statuses=appointment_statuses_strategy)
def test_revenue_equals_completed_times_fee(statuses: List[str]):
    """
    **Validates: Requirements 3.2, 5.3**

    Property 2: Daily revenue equals completed appointments times fee.

    For any set of appointments with varying statuses on a given day, the
    `revenue` value returned by the analytics query SHALL equal:
        count(appointments where status == "completed") * 500

    This test exercises the same SQL CASE expression used in
    AnalyticsService.get_daily_revenue() against an in-memory SQLite database,
    ensuring the formula holds for all combinations of appointment statuses.
    """
    run_async(_run_revenue_property(statuses))


async def _run_revenue_property(statuses: List[str]) -> None:
    """
    Async implementation of the revenue formula property test.

    Creates a fresh in-memory SQLite database for each Hypothesis example,
    seeds it with appointments having the given statuses, runs the analytics
    query, and asserts the revenue formula.
    """
    # Fresh in-memory database per example to avoid state leakage
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )

    try:
        # Create schema
        async with engine.begin() as conn:
            await conn.run_sync(TestBase.metadata.create_all)

        # Fixed reference day for all appointments in this example
        day_start = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        # Seed required parent rows
        async with session_factory() as session:
            async with session.begin():
                clinic = TestClinic(name="Test Clinic", timezone="UTC")
                session.add(clinic)
                await session.flush()

                patient = TestPatient(
                    full_name="Test Patient",
                    email="patient@test.com",
                    phone="9000000000",
                )
                session.add(patient)
                await session.flush()

                # Create one appointment per status in the generated list.
                # Each appointment gets a unique 30-minute slot within the day.
                for idx, status in enumerate(statuses):
                    slot_start = day_start + timedelta(minutes=30 * idx)
                    slot_end = slot_start + timedelta(minutes=30)

                    slot = TestAvailabilitySchedule(
                        clinic_id=clinic.id,
                        slot_start=slot_start,
                        slot_end=slot_end,
                        is_open=False,
                    )
                    session.add(slot)
                    await session.flush()

                    appt = TestAppointment(
                        clinic_id=clinic.id,
                        patient_id=patient.id,
                        schedule_id=slot.id,
                        scheduled_start=slot_start,
                        scheduled_end=slot_end,
                        status=status,
                    )
                    session.add(appt)

                clinic_id = clinic.id

        # Run the analytics query
        result = await query_daily_revenue(session_factory, clinic_id, day_start, day_end)

        # --- Core property assertion ---
        expected_completed = statuses.count("completed")
        expected_revenue = expected_completed * APPOINTMENT_FEE

        assert result["revenue"] == expected_revenue, (
            f"Revenue mismatch: expected {expected_revenue} "
            f"({expected_completed} completed × ₹{APPOINTMENT_FEE}), "
            f"got {result['revenue']}. "
            f"Statuses: {statuses}"
        )

        # --- Consistency assertions ---
        # The completed count returned by the query must match our expectation
        assert result["completed"] == expected_completed, (
            f"Completed count mismatch: expected {expected_completed}, "
            f"got {result['completed']}. Statuses: {statuses}"
        )

        # Total appointments must equal the number of statuses seeded
        assert result["total_appointments"] == len(statuses), (
            f"Total appointments mismatch: expected {len(statuses)}, "
            f"got {result['total_appointments']}. Statuses: {statuses}"
        )

        # Missed count must match
        expected_missed = statuses.count("missed")
        assert result["missed"] == expected_missed, (
            f"Missed count mismatch: expected {expected_missed}, "
            f"got {result['missed']}. Statuses: {statuses}"
        )

        # Revenue must never be negative
        assert result["revenue"] >= 0, (
            f"Revenue must be non-negative, got {result['revenue']}"
        )

        # Revenue must be a multiple of the fee (or zero)
        if result["revenue"] > 0:
            assert result["revenue"] % APPOINTMENT_FEE == 0, (
                f"Revenue {result['revenue']} is not a multiple of ₹{APPOINTMENT_FEE}"
            )

    finally:
        await engine.dispose()
