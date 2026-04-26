import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.database import (
    AsyncSessionFactory,
    Patient,
    Availability_Schedule,
    Appointment,
    book_appointment_slot,
)

router = APIRouter(prefix="/voice", tags=["voice"])
IST = ZoneInfo("Asia/Kolkata")

@router.post("")
@router.post("/")
async def voice_incoming(From: str = Form(None)):
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="1" action="/voice/menu" method="POST">
        <Say>Welcome to City Health Clinic. Press 1 to book a new appointment. Press 2 to check the status of your existing appointment.</Say>
    </Gather>
    <Say>We didn't receive any input. Goodbye.</Say>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

@router.post("/menu")
async def voice_menu(From: str = Form(None), Digits: str = Form(None)):
    if Digits == "1":
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather numDigits="4" action="/voice/book" method="POST">
        <Say>Please enter the 4 digit date for your appointment in Month Month Day Day format. For example, for April 24th, enter 0 4 2 4.</Say>
    </Gather>
    <Say>We didn't receive any input. Goodbye.</Say>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
    elif Digits == "2":
        if not From:
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, we could not identify your phone number. Goodbye.</Say>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        phone_number = From
        if phone_number.startswith("whatsapp:"):
            phone_number = phone_number.replace("whatsapp:", "")
            
        async with AsyncSessionFactory() as session:
            patient_stmt = select(Patient).where(Patient.phone == phone_number).limit(1)
            patient_result = await session.execute(patient_stmt)
            patient = patient_result.scalar_one_or_none()
            
            if not patient:
                twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>We could not find any records for your phone number. Goodbye.</Say>
</Response>"""
                return Response(content=twiml, media_type="application/xml")
                
            appt_stmt = (
                select(Appointment)
                .where(Appointment.patient_id == patient.id)
                .order_by(Appointment.scheduled_start.desc())
                .limit(1)
            )
            appt_result = await session.execute(appt_stmt)
            appt = appt_result.scalar_one_or_none()
            
            if not appt:
                twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>You have no existing appointments. Goodbye.</Say>
</Response>"""
            else:
                date_str = appt.scheduled_start.astimezone(IST).strftime("%B %d at %I:%M %p")
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>You have an appointment on {date_str}. The status is {appt.status}. Goodbye.</Say>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
    else:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Invalid option selected. Goodbye.</Say>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

@router.post("/book")
async def voice_book(From: str = Form(None), Digits: str = Form(None)):
    if not Digits or len(Digits) != 4:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Invalid date format entered. Goodbye.</Say>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    try:
        month = int(Digits[0:2])
        day = int(Digits[2:4])
        now = datetime.now(IST)
        year = now.year
        
        if month < now.month:
            year += 1
            
        target_date = datetime(year, month, day).date()
    except ValueError:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>The date you entered is invalid. Goodbye.</Say>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    phone_number = From or "Unknown"
    if phone_number.startswith("whatsapp:"):
        phone_number = phone_number.replace("whatsapp:", "")

    async with AsyncSessionFactory() as session:
        patient_stmt = select(Patient).where(Patient.phone == phone_number).limit(1)
        patient_result = await session.execute(patient_stmt)
        patient = patient_result.scalar_one_or_none()

        if not patient:
            async with session.begin():
                digits_only = "".join(ch for ch in phone_number if ch.isdigit())
                base = digits_only or "unknown"
                patient = Patient(
                    full_name="Voice Caller",
                    email=f"voice_{base}@clinic.local",
                    phone=phone_number,
                )
                session.add(patient)
            
        stmt = (
            select(Availability_Schedule)
            .where(
                Availability_Schedule.clinic_id == 1,
                Availability_Schedule.is_open == True
            )
            .order_by(Availability_Schedule.slot_start)
        )
        
        result = await session.execute(stmt)
        available_slots = result.scalars().all()
        
        target_slot = None
        for slot in available_slots:
            slot_date = slot.slot_start.astimezone(IST).date()
            if slot_date == target_date:
                target_slot = slot
                break
                
        if not target_slot:
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, there are no available slots for that date. Goodbye.</Say>
</Response>"""
            return Response(content=twiml, media_type="application/xml")
            
        try:
            appt = await book_appointment_slot(
                session=session,
                clinic_id=target_slot.clinic_id,
                patient_id=patient.id,
                slot_start=target_slot.slot_start,
                slot_end=target_slot.slot_end
            )
            date_str = appt.scheduled_start.astimezone(IST).strftime("%B %d at %I:%M %p")
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Your appointment has been successfully booked for {date_str}. Your booking ID is {appt.id}. Goodbye.</Say>
</Response>"""
            return Response(content=twiml, media_type="application/xml")
        except Exception as e:
            print(f"Voice booking error: {e}")
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, that slot was just taken. Please call back to try again.</Say>
</Response>"""
            return Response(content=twiml, media_type="application/xml")
