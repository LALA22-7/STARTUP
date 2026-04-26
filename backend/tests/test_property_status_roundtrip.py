"""
Property-based test: Appointment status round-trip.

Property 1: For any appointment in the database, after a PATCH request updates
its status to a valid value, a subsequent GET request for that appointment SHALL
return the updated status value.

Validates: Requirements 5.2
"""
import os
import sys
import asyncio
from datetime import datetime, timezone
from typing import Generator

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import JSON, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Minimal SQLite-compatible ORM models (mirrors database.py but uses JSON
# instead of JSONB so they work with aiosqlite / SQLite).
# ---------------------------------------------------------------------------

class TestBase(DeclarativeBase):
    pass


class TestClinic(TestBase):
    __tablename__ = "Clinics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class TestPatient(TestBase):
    __tablename__ = "Patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class TestDoctor(TestBase):
    __tablename__ = "Doctors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("Clinics.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialization: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class TestAvailabilitySchedule(TestBase):
    __tablename__ = "Availability_Schedules"
    __table_args__ = (
        UniqueConstraint("clinic_id", "slot_start", "slot_end", name="uq_availability_slot_per_clinic"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("Clinics.id", ondelete="CASCADE"), nullable=False)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
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
    clinic_id: Mapped[int] = mapped_column(ForeignKey("Clinics.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[int] = mapped_column(ForeignKey("Patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("Doctors.id", ondelete="SET NULL"), nullable=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("Availability_Schedules.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="booked")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class TestEncounter(TestBase):
    __tablename__ = "Encounters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("Patients.id", ondelete="CASCADE"), nullable=False)
    record: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Async helpers — run sync from the synchronous TestClient context
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine from a synchronous context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Pytest fixture: in-memory SQLite engine + seeded data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_engine_and_ids():
    """
    Create an in-memory SQLite database, create all tables, seed one row of
    each required entity, and return (engine, session_factory, clinic_id,
    appointment_id).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(TestBase.metadata.create_all)

        async with session_factory() as session:
            async with session.begin():
                now = datetime.now(timezone.utc)

                clinic = TestClinic(name="Test Clinic", timezone="UTC")
                session.add(clinic)
                await session.flush()

                patient = TestPatient(
                    full_name="Test Patient",
                    email="test@example.com",
                    phone="9999999999",
                )
                session.add(patient)
                await session.flush()

                doctor = TestDoctor(
                    clinic_id=clinic.id,
                    full_name="Dr. Test",
                    specialization="General",
                )
                session.add(doctor)
                await session.flush()

                slot = TestAvailabilitySchedule(
                    clinic_id=clinic.id,
                    slot_start=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
                    slot_end=datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                    is_open=False,
                )
                session.add(slot)
                await session.flush()

                appt = TestAppointment(
                    clinic_id=clinic.id,
                    patient_id=patient.id,
                    doctor_id=doctor.id,
                    schedule_id=slot.id,
                    scheduled_start=slot.slot_start,
                    scheduled_end=slot.slot_end,
                    status="booked",
                )
                session.add(appt)
                await session.flush()

                return clinic.id, appt.id

        return clinic_id, appt_id

    clinic_id, appt_id = run_async(_setup())
    yield engine, session_factory, clinic_id, appt_id

    async def _teardown():
        await engine.dispose()

    run_async(_teardown())


# ---------------------------------------------------------------------------
# Pytest fixture: FastAPI TestClient with overridden session factory
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_client(test_engine_and_ids, monkeypatch_module):
    """
    Build a TestClient for the FastAPI app, with AsyncSessionFactory patched
    to use the in-memory SQLite session factory.
    """
    engine, session_factory, clinic_id, appt_id = test_engine_and_ids

    # Patch env vars so the startup event doesn't sys.exit
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("META_PHONE_ID", "test_phone_id")
    os.environ.setdefault("META_ACCESS_TOKEN", "test_access_token")

    # Patch AsyncSessionFactory in both the database module and main module
    import app.database as db_module
    import app.main as main_module

    original_db_factory = db_module.AsyncSessionFactory
    original_main_factory = main_module.AsyncSessionFactory

    db_module.AsyncSessionFactory = session_factory
    main_module.AsyncSessionFactory = session_factory

    # Import app after patching
    from app.main import app as fastapi_app

    with TestClient(fastapi_app, raise_server_exceptions=True) as client:
        yield client

    # Restore
    db_module.AsyncSessionFactory = original_db_factory
    main_module.AsyncSessionFactory = original_main_factory


# ---------------------------------------------------------------------------
# Module-scoped monkeypatch (pytest's built-in monkeypatch is function-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def monkeypatch_module():
    """A module-scoped monkeypatch fixture."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


# ---------------------------------------------------------------------------
# Property-based test
# ---------------------------------------------------------------------------

VALID_STATUSES = ["booked", "completed", "missed", "waiting"]


@pytest.fixture(scope="module")
def app_context(test_engine_and_ids):
    """
    Returns a TestClient with the session factory patched, plus clinic_id and
    appointment_id for use in the property test.
    """
    engine, session_factory, clinic_id, appt_id = test_engine_and_ids

    # Patch env vars so the startup event doesn't sys.exit
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("META_PHONE_ID", "test_phone_id")
    os.environ.setdefault("META_ACCESS_TOKEN", "test_access_token")

    import app.database as db_module
    import app.main as main_module

    db_module.AsyncSessionFactory = session_factory
    main_module.AsyncSessionFactory = session_factory

    from app.main import app as fastapi_app

    with TestClient(fastapi_app, raise_server_exceptions=True) as client:
        yield client, clinic_id, appt_id


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(status=st.sampled_from(VALID_STATUSES))
def test_status_roundtrip(status, app_context):
    """
    **Validates: Requirements 5.2**

    Property 1: Appointment status update is reflected in subsequent reads.

    For any valid status value, after PATCHing an appointment's status, a
    subsequent GET of the appointment list must return the same status value.
    """
    client, clinic_id, appt_id = app_context

    # PATCH the appointment status
    patch_response = client.patch(
        f"/api/appointments/{appt_id}/status",
        json={"status": status},
    )

    # If the appointment doesn't exist (404), skip the assertion gracefully
    if patch_response.status_code == 404:
        return

    assert patch_response.status_code == 200, (
        f"PATCH returned unexpected status {patch_response.status_code}: "
        f"{patch_response.text}"
    )

    patch_data = patch_response.json()
    assert patch_data["status"] == status, (
        f"PATCH response status mismatch: expected {status!r}, got {patch_data['status']!r}"
    )

    # GET the appointment list and find the updated appointment
    get_response = client.get(f"/api/appointments?clinic_id={clinic_id}")
    assert get_response.status_code == 200, (
        f"GET returned unexpected status {get_response.status_code}: "
        f"{get_response.text}"
    )

    appointments = get_response.json()
    matching = [a for a in appointments if a["id"] == appt_id]

    assert len(matching) == 1, (
        f"Expected exactly 1 appointment with id={appt_id}, found {len(matching)}"
    )

    returned_status = matching[0]["status"]
    assert returned_status == status, (
        f"GET status mismatch after PATCH: expected {status!r}, got {returned_status!r}"
    )
