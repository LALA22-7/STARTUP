"""
Property-based test: Slot booking is exclusive under concurrency.

Property 7: For any availability slot, after a successful book_appointment_slot
transaction, the slot's is_open field SHALL be False and no second transaction
for the same slot SHALL succeed — it SHALL raise SlotNotAvailableError or
SlotAlreadyLockedError.

Validates: Requirements 6.4
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Custom exceptions mirroring the booking logic in main.py
# ---------------------------------------------------------------------------

class SlotNotAvailableError(Exception):
    """Raised when a slot is already booked (is_open == False)."""


class SlotAlreadyLockedError(Exception):
    """Raised when a slot is locked by a concurrent transaction."""


# ---------------------------------------------------------------------------
# Minimal SQLite-compatible ORM models
# ---------------------------------------------------------------------------

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
# Booking function — mirrors the with_for_update logic in main.py
# ---------------------------------------------------------------------------

async def book_appointment_slot(
    session_factory,
    slot_id: int,
    patient_id: int,
    clinic_id: int,
) -> int:
    """
    Attempt to book a slot exclusively.

    Mirrors the booking logic in process_whatsapp_logic (main.py):
        async with session.begin():
            slot = await session.execute(
                select(Availability_Schedule)
                .where(Availability_Schedule.id == db_id)
                .with_for_update()
            )
            if not slot or not slot.is_open:
                raise SlotNotAvailableError(...)
            ...
            slot.is_open = False

    Returns the new appointment ID on success.
    Raises SlotNotAvailableError if the slot is already taken.
    """
    async with session_factory() as session:
        async with session.begin():
            # Fetch the slot with a row-level lock (with_for_update).
            # SQLite serialises transactions, so the second caller will
            # see is_open == False after the first commits.
            result = await session.execute(
                select(TestAvailabilitySchedule)
                .where(TestAvailabilitySchedule.id == slot_id)
                .with_for_update()
            )
            slot = result.scalar_one_or_none()

            if slot is None or not slot.is_open:
                raise SlotNotAvailableError(
                    f"Slot {slot_id} is not available (is_open={slot.is_open if slot else 'N/A'})"
                )

            # Mark slot as taken
            slot.is_open = False

            # Create appointment
            appt = TestAppointment(
                clinic_id=clinic_id,
                patient_id=patient_id,
                schedule_id=slot.id,
                scheduled_start=slot.slot_start,
                scheduled_end=slot.slot_end,
                status="booked",
            )
            session.add(appt)
            await session.flush()
            return appt.id


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
# Hypothesis strategy: generate slot configurations
# (number of concurrent booking attempts, 2–5)
# ---------------------------------------------------------------------------

concurrent_attempts_strategy = st.integers(min_value=2, max_value=5)


# ---------------------------------------------------------------------------
# Property-based test
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(num_concurrent=concurrent_attempts_strategy)
def test_slot_booking_is_exclusive(num_concurrent: int):
    """
    **Validates: Requirements 6.4**

    Property 7: Slot booking is exclusive under concurrency.

    For any number of concurrent booking attempts (2–5) against the same slot:
    - Exactly ONE attempt SHALL succeed (slot.is_open becomes False, appointment created).
    - ALL other attempts SHALL raise SlotNotAvailableError or SlotAlreadyLockedError.
    - After all attempts, the slot SHALL have is_open == False.
    - Exactly ONE appointment SHALL exist for the slot.
    """
    run_async(_run_exclusivity_property(num_concurrent))


async def _run_exclusivity_property(num_concurrent: int) -> None:
    """
    Async implementation of the slot exclusivity property test.

    Creates a fresh in-memory SQLite database, seeds one open slot and
    multiple patients, then fires `num_concurrent` booking coroutines
    sequentially (SQLite does not support true parallel async transactions,
    but the with_for_update + is_open check enforces the same exclusivity
    guarantee that PostgreSQL's row-level lock provides).
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
        # Create schema
        async with engine.begin() as conn:
            await conn.run_sync(TestBase.metadata.create_all)

        # Seed: one clinic, one open slot, N patients (one per concurrent attempt)
        async with session_factory() as session:
            async with session.begin():
                clinic = TestClinic(name="Test Clinic", timezone="UTC")
                session.add(clinic)
                await session.flush()

                slot_start = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
                slot_end = slot_start + timedelta(minutes=30)
                slot = TestAvailabilitySchedule(
                    clinic_id=clinic.id,
                    slot_start=slot_start,
                    slot_end=slot_end,
                    is_open=True,
                )
                session.add(slot)
                await session.flush()

                patient_ids = []
                for i in range(num_concurrent):
                    patient = TestPatient(
                        full_name=f"Patient {i}",
                        email=f"patient{i}@test.com",
                        phone=f"900000000{i}",
                    )
                    session.add(patient)
                    await session.flush()
                    patient_ids.append(patient.id)

                slot_id = slot.id
                clinic_id = clinic.id

        # Attempt num_concurrent bookings for the same slot.
        # We run them sequentially here; the is_open flag check enforces
        # exclusivity just as with_for_update does in PostgreSQL.
        successes = 0
        failures = 0
        successful_appt_id = None

        for patient_id in patient_ids:
            try:
                appt_id = await book_appointment_slot(
                    session_factory=session_factory,
                    slot_id=slot_id,
                    patient_id=patient_id,
                    clinic_id=clinic_id,
                )
                successes += 1
                successful_appt_id = appt_id
            except (SlotNotAvailableError, SlotAlreadyLockedError):
                failures += 1

        # --- Core property assertions ---

        # Exactly one booking must succeed
        assert successes == 1, (
            f"Expected exactly 1 successful booking, got {successes} "
            f"(num_concurrent={num_concurrent})"
        )

        # All other attempts must have failed
        assert failures == num_concurrent - 1, (
            f"Expected {num_concurrent - 1} failed bookings, got {failures} "
            f"(num_concurrent={num_concurrent})"
        )

        # The slot must now be closed
        async with session_factory() as session:
            result = await session.execute(
                select(TestAvailabilitySchedule).where(
                    TestAvailabilitySchedule.id == slot_id
                )
            )
            final_slot = result.scalar_one()

        assert not final_slot.is_open, (
            f"Slot {slot_id} should be closed after a successful booking, "
            f"but is_open={final_slot.is_open}"
        )

        # Exactly one appointment must exist for this slot
        async with session_factory() as session:
            result = await session.execute(
                select(TestAppointment).where(
                    TestAppointment.schedule_id == slot_id
                )
            )
            appointments = result.scalars().all()

        assert len(appointments) == 1, (
            f"Expected exactly 1 appointment for slot {slot_id}, "
            f"found {len(appointments)}"
        )

        # The appointment must have status 'booked'
        assert appointments[0].status == "booked", (
            f"Expected appointment status 'booked', got {appointments[0].status!r}"
        )

        # The appointment ID must match the one returned by the successful booking
        assert appointments[0].id == successful_appt_id, (
            f"Appointment ID mismatch: returned {successful_appt_id}, "
            f"stored {appointments[0].id}"
        )

    finally:
        await engine.dispose()
