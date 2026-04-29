import sys
import os

# Ensure the backend/ directory is on sys.path so `app` resolves correctly
# whether this script is run directly or as a module.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from datetime import datetime, timedelta, timezone
from app.database import engine, Base, Clinic, Patient, Availability_Schedule, Encounter, CallLog, Doctor, Appointment, AsyncSessionFactory
from sqlalchemy import text

async def setup_database():
    print("[db] Connecting to PostgreSQL...")
    
    # 1. Build the Tables
    async with engine.begin() as conn:
        print("[db] Building tables...")
        # We drop all tables first so you can run this script multiple times safely while testing
        await conn.run_sync(Base.metadata.drop_all) 
        await conn.run_sync(Base.metadata.create_all)
        print("[db] Tables built successfully")

        # Ensure reminder columns exist (safe to run on existing DBs too)
        await conn.execute(
            text('ALTER TABLE "Appointments" ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ')
        )
        await conn.execute(
            text('ALTER TABLE "Appointments" ADD COLUMN IF NOT EXISTS confirmed BOOLEAN NOT NULL DEFAULT FALSE')
        )
        print("[db] Reminder columns verified")

    # 2. Inject Test Data
    async with AsyncSessionFactory() as session:
        print("[db] Injecting test data...")
        
        # Create the Clinic
        clinic = Clinic(name="City Health Clinic", timezone="Asia/Kolkata")
        session.add(clinic)
        await session.commit()
        await session.refresh(clinic)

        # Create the Test Patient (matching your WhatsApp mock number)
        patient = Patient(full_name="Test Patient", email="test@example.com", phone="919876543210")
        session.add(patient)
        await session.commit()
        await session.refresh(patient)

        # Create Test Doctors
        doctors = [
            Doctor(
                clinic_id=clinic.id,
                full_name="Dr. Rajesh Smith",
                specialization="General Medicine",
                email="rajesh@clinic.com",
                phone="+919876543211",
                is_active=True
            ),
            Doctor(
                clinic_id=clinic.id,
                full_name="Dr. Priya Sharma",
                specialization="Pediatrics",
                email="priya@clinic.com",
                phone="+919876543212",
                is_active=True
            )
        ]
        session.add_all(doctors)
        await session.commit()
        await session.refresh(doctors[0])
        await session.refresh(doctors[1])

        # Create Available Slots for Tomorrow (UTC time)
        tomorrow = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        slots = [
            Availability_Schedule(
                clinic_id=clinic.id, 
                slot_start=tomorrow.replace(hour=3, minute=30), # 9:00 AM IST
                slot_end=tomorrow.replace(hour=4, minute=0),
                is_open=True
            ),
            Availability_Schedule(
                clinic_id=clinic.id, 
                slot_start=tomorrow.replace(hour=5, minute=0), # 10:30 AM IST
                slot_end=tomorrow.replace(hour=5, minute=30),
                is_open=True
            ),
            Availability_Schedule(
                clinic_id=clinic.id, 
                slot_start=tomorrow.replace(hour=11, minute=30), # 5:00 PM IST
                slot_end=tomorrow.replace(hour=12, minute=0),
                is_open=True
            )
        ]
        
        session.add_all(slots)
        await session.commit()

        # Get the first slot for creating an appointment
        first_slot = slots[0]
        await session.refresh(first_slot)

        # Create a Test Appointment
        appointment = Appointment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctors[0].id,
            schedule_id=first_slot.id,
            scheduled_start=first_slot.slot_start,
            scheduled_end=first_slot.slot_end,
            status="booked"
        )
        session.add(appointment)
        await session.commit()

        # Create Call Logs
        call_logs = [
            CallLog(call_type="whatsapp", direction="incoming"),
            CallLog(call_type="voice", direction="incoming"),
            CallLog(call_type="whatsapp", direction="outgoing")
        ]
        session.add_all(call_logs)

        # Create Encounters
        encounters = [
            Encounter(
                patient_id=patient.id, 
                record={"notes": "Patient reported mild fever and cough.", "vitals": {"temp": 99.5, "bp": "120/80"}}
            ),
            Encounter(
                patient_id=patient.id, 
                record={"notes": "Follow-up. Fever subsidized. Prescribed rest.", "vitals": {"temp": 98.6, "bp": "118/79"}}
            )
        ]
        session.add_all(encounters)

        await session.commit()

        print("[db] Test data injected successfully")
        print(f"[db] Clinic ID: {clinic.id}")
        print(f"[db] Patient ID: {patient.id}")
        print("Database is ready for bookings.")

if __name__ == "__main__":
    asyncio.run(setup_database())