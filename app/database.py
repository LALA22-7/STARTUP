from __future__ import annotations

import os
from datetime import datetime
from dotenv import load_dotenv  # <-- ADD THIS

# Load the .env file BEFORE trying to read the DATABASE_URL
load_dotenv()                   # <-- ADD THIS

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, MetaData, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Keep DB credentials outside source code in production.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/clinic_booking",
)

# ... rest of the file stays exactly the same ...

metadata = MetaData()


class Base(DeclarativeBase):
    metadata = metadata


class Clinic(Base):
    __tablename__ = "Clinics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Patient(Base):
    __tablename__ = "Patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Availability_Schedule(Base):
    __tablename__ = "Availability_Schedules"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "slot_start",
            "slot_end",
            name="uq_availability_slot_per_clinic",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("Clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Appointment(Base):
    __tablename__ = "Appointments"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "scheduled_start",
            "scheduled_end",
            name="uq_appointment_slot_per_clinic",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("Clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("Patients.id", ondelete="CASCADE"), nullable=False, index=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("Availability_Schedules.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="booked")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionFactory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class BookingError(Exception):
    pass


class SlotAlreadyLockedError(BookingError):
    pass


class SlotNotAvailableError(BookingError):
    pass


class InvalidBookingError(BookingError):
    pass


class EntityNotFoundError(BookingError):
    pass


def _is_lock_not_available(exc: OperationalError) -> bool:
    # PostgreSQL lock-not-available SQLSTATE: 55P03.
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == "55P03":
        return True
    return "could not obtain lock on row" in str(exc).lower()


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def book_appointment_slot(
    session: AsyncSession,
    *,
    clinic_id: int,
    patient_id: int,
    slot_start: datetime,
    slot_end: datetime,
) -> Appointment:
    """Book one appointment slot safely under concurrency.

    Uses row-level locking on Availability_Schedule so only one transaction
    can claim the same slot at a time.
    """
    if slot_start >= slot_end:
        raise InvalidBookingError("slot_start must be earlier than slot_end")

    try:
        async with session.begin():
            clinic = await session.get(Clinic, clinic_id)
            if clinic is None:
                raise EntityNotFoundError("Clinic not found")

            patient = await session.get(Patient, patient_id)
            if patient is None:
                raise EntityNotFoundError("Patient not found")

            try:
                availability_stmt = (
                    select(Availability_Schedule)
                    .where(
                        Availability_Schedule.clinic_id == clinic_id,
                        Availability_Schedule.slot_start == slot_start,
                        Availability_Schedule.slot_end == slot_end,
                    )
                    .with_for_update(nowait=True)
                )
                availability_result = await session.execute(availability_stmt)
            except OperationalError as exc:
                if _is_lock_not_available(exc):
                    raise SlotAlreadyLockedError("Slot is currently being booked by another request") from exc
                raise

            availability = availability_result.scalar_one_or_none()
            if availability is None:
                raise EntityNotFoundError("Slot not found")

            if not availability.is_open:
                raise SlotNotAvailableError("Slot is no longer available")

            appointment = Appointment(
                clinic_id=clinic_id,
                patient_id=patient_id,
                schedule_id=availability.id,
                scheduled_start=slot_start,
                scheduled_end=slot_end,
                status="booked",
            )
            session.add(appointment)

            availability.is_open = False

        await session.refresh(appointment)
        return appointment

    except IntegrityError as exc:
        await session.rollback()
        raise SlotNotAvailableError("The selected slot has already been booked") from exc