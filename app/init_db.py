import asyncio
from datetime import datetime, timedelta, timezone
from app.database import engine, Base, Clinic, Patient, Availability_Schedule, AsyncSessionFactory

async def setup_database():
    print("🔌 Connecting to Docker PostgreSQL...")
    
    # 1. Build the Tables
    async with engine.begin() as conn:
        print("🏗️  Building tables...")
        # We drop all tables first so you can run this script multiple times safely while testing
        await conn.run_sync(Base.metadata.drop_all) 
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Tables built successfully!")

    # 2. Inject Test Data
    async with AsyncSessionFactory() as session:
        print("💉 Injecting test data...")
        
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

        print("✅ Test data injected successfully!")
        print(f"🏥 Clinic ID: {clinic.id}")
        print(f"👤 Patient ID: {patient.id}")
        print("Database is ready for bookings.")

if __name__ == "__main__":
    asyncio.run(setup_database())