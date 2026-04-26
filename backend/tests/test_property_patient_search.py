"""
Property-based test: Patient search is a subset filter.

Property 4: For any non-empty search string, every patient returned by
`GET /api/patients?search=<query>` SHALL have a `full_name` or `phone` that
contains the query string (case-insensitive). No patient whose name and phone
both exclude the query string SHALL appear in the results.

Validates: Requirements 4.4, 5.5
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import pytest
from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Minimal SQLite-compatible ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class Clinic(Base):
    __tablename__ = "Clinics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class Patient(Base):
    __tablename__ = "Patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AvailabilitySchedule(Base):
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


class Appointment(Base):
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
# Pure search filter — mirrors the SQL logic in GET /api/patients
# ---------------------------------------------------------------------------

def apply_patient_search(patients: List[dict], search: str) -> List[dict]:
    """
    Filter a list of patient dicts by search string.

    Mirrors the SQL filter in GET /api/patients:
        WHERE LOWER(full_name) LIKE LOWER('%search%')
           OR phone LIKE '%search%'
    """
    pattern = search.lower()
    return [
        p for p in patients
        if pattern in (p.get("full_name") or "").lower()
        or pattern in (p.get("phone") or "")
    ]


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine from a synchronous context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def query_patients_with_search(
    session_factory,
    clinic_id: int,
    search: Optional[str],
) -> List[dict]:
    """
    Execute the same patient search query as GET /api/patients against the
    provided session factory.

    Returns a list of patient dicts with keys: id, full_name, phone, email.
    """
    async with session_factory() as session:
        # Subquery: patient IDs that have at least one appointment for this clinic
        clinic_patient_ids_stmt = select(Appointment.patient_id).where(
            Appointment.clinic_id == clinic_id
        ).distinct()

        stmt = select(Patient).where(Patient.id.in_(clinic_patient_ids_stmt))

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    func.lower(Patient.full_name).like(func.lower(pattern)),
                    Patient.phone.like(pattern),
                )
            )

        result = await session.execute(stmt)
        patients = result.scalars().all()

    return [
        {"id": p.id, "full_name": p.full_name, "phone": p.phone, "email": p.email}
        for p in patients
    ]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for a single patient record
@st.composite
def patient_record_strategy(draw, index: int):
    """Generate a patient dict with a unique index-based email."""
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
        min_size=1,
        max_size=40,
    ))
    # Phone: either None or a string of 7–15 digits
    phone = draw(st.one_of(
        st.none(),
        st.text(alphabet="0123456789", min_size=7, max_size=15),
    ))
    return {"full_name": name, "phone": phone, "index": index}


# Strategy for a list of 1–10 patients
@st.composite
def patient_list_strategy(draw):
    n = draw(st.integers(min_value=1, max_value=10))
    return [draw(patient_record_strategy(i)) for i in range(n)]


# Strategy for a non-empty search string (ASCII printable, 1–10 chars)
search_string_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(
    patients=patient_list_strategy(),
    search=search_string_strategy,
)
def test_patient_search_returns_subset(patients: List[dict], search: str):
    """
    **Validates: Requirements 4.4, 5.5**

    Property 4: Patient search is a subset filter.

    For any non-empty search string, every patient returned by the search
    SHALL have a full_name or phone that contains the query (case-insensitive).
    No patient whose name and phone both exclude the query SHALL appear.
    """
    run_async(_run_search_subset_property(patients, search))


async def _run_search_subset_property(patients: List[dict], search: str) -> None:
    """
    Async implementation of the patient search subset property test.

    Seeds an in-memory SQLite database with the generated patients (each
    linked to the clinic via an appointment), runs the search query, and
    asserts the subset property.
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

        async with session_factory() as session:
            async with session.begin():
                clinic = Clinic(name="Test Clinic", timezone="UTC")
                session.add(clinic)
                await session.flush()

                seeded_patients = []
                for p_data in patients:
                    idx = p_data["index"]
                    patient = Patient(
                        full_name=p_data["full_name"],
                        email=f"patient_{idx}_{id(p_data)}@test.com",
                        phone=p_data["phone"],
                    )
                    session.add(patient)
                    await session.flush()

                    # Create a slot and appointment so the patient is linked to the clinic
                    from datetime import timedelta
                    slot_start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(hours=idx)
                    slot_end = slot_start + timedelta(minutes=30)

                    slot = AvailabilitySchedule(
                        clinic_id=clinic.id,
                        slot_start=slot_start,
                        slot_end=slot_end,
                        is_open=False,
                    )
                    session.add(slot)
                    await session.flush()

                    appt = Appointment(
                        clinic_id=clinic.id,
                        patient_id=patient.id,
                        schedule_id=slot.id,
                        scheduled_start=slot_start,
                        scheduled_end=slot_end,
                        status="booked",
                    )
                    session.add(appt)
                    seeded_patients.append({"full_name": p_data["full_name"], "phone": p_data["phone"]})

                clinic_id = clinic.id

        # Run the search query
        results = await query_patients_with_search(session_factory, clinic_id, search)

        # --- Core property assertion: every result must match the search ---
        pattern = search.lower()
        for result in results:
            name_matches = pattern in (result["full_name"] or "").lower()
            phone_matches = pattern in (result["phone"] or "")
            assert name_matches or phone_matches, (
                f"Patient {result!r} was returned for search={search!r} "
                f"but neither full_name nor phone contains the query."
            )

        # --- Completeness assertion: no matching patient should be excluded ---
        # Compute expected matches from seeded data
        expected_matches = apply_patient_search(seeded_patients, search)
        # The result count must equal the number of patients that match
        assert len(results) == len(expected_matches), (
            f"Search for {search!r} returned {len(results)} results, "
            f"expected {len(expected_matches)}. "
            f"Seeded patients: {seeded_patients}"
        )

    finally:
        await engine.dispose()


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(patients=patient_list_strategy())
def test_empty_search_returns_all_patients(patients: List[dict]):
    """
    **Validates: Requirements 4.4, 5.5**

    When no search string is provided, all patients linked to the clinic
    SHALL be returned (no filtering applied).
    """
    run_async(_run_no_search_property(patients))


async def _run_no_search_property(patients: List[dict]) -> None:
    """Verify that omitting the search param returns all clinic patients."""
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

        async with session_factory() as session:
            async with session.begin():
                clinic = Clinic(name="Test Clinic", timezone="UTC")
                session.add(clinic)
                await session.flush()

                from datetime import timedelta
                for p_data in patients:
                    idx = p_data["index"]
                    patient = Patient(
                        full_name=p_data["full_name"],
                        email=f"patient_{idx}_{id(p_data)}@test.com",
                        phone=p_data["phone"],
                    )
                    session.add(patient)
                    await session.flush()

                    slot_start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(hours=idx)
                    slot_end = slot_start + timedelta(minutes=30)

                    slot = AvailabilitySchedule(
                        clinic_id=clinic.id,
                        slot_start=slot_start,
                        slot_end=slot_end,
                        is_open=False,
                    )
                    session.add(slot)
                    await session.flush()

                    appt = Appointment(
                        clinic_id=clinic.id,
                        patient_id=patient.id,
                        schedule_id=slot.id,
                        scheduled_start=slot_start,
                        scheduled_end=slot_end,
                        status="booked",
                    )
                    session.add(appt)

                clinic_id = clinic.id

        # No search param — should return all patients
        results = await query_patients_with_search(session_factory, clinic_id, search=None)

        assert len(results) == len(patients), (
            f"Expected {len(patients)} patients without search filter, "
            f"got {len(results)}"
        )

    finally:
        await engine.dispose()
