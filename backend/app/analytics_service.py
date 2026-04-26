"""
Analytics Service for Revenue Tracking and Insights
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional

from sqlalchemy import select, func, distinct, case
import pandas as pd

from app.database import AsyncSessionFactory, Appointment, Patient

IST = ZoneInfo("Asia/Kolkata")


class AnalyticsService:
    """Service for generating clinic analytics and revenue reports"""
    
    def __init__(self, clinic_id: int = 1):
        self.clinic_id = clinic_id
    
    async def get_daily_revenue(self, date: Optional[datetime] = None) -> Dict:
        """Get revenue for a specific date (default: today)"""
        if date is None:
            date = datetime.now(IST)
        
        day_start = datetime.combine(date.date(), datetime.min.time(), tzinfo=IST)
        day_end = day_start + timedelta(days=1)
        
        async with AsyncSessionFactory() as session:
            stmt = (
                select(
                    func.count(Appointment.id).label("total_appointments"),
                    func.sum(
                        case(
                            (Appointment.status == "completed", 500),
                            else_=0,
                        )
                    ).label("revenue"),
                )
                .where(
                    Appointment.clinic_id == self.clinic_id,
                    Appointment.scheduled_start >= day_start.astimezone(timezone.utc),
                    Appointment.scheduled_start < day_end.astimezone(timezone.utc),
                )
            )
            
            result = await session.execute(stmt)
            row = result.first()
            
            return {
                "date": date.strftime("%Y-%m-%d"),
                "total_appointments": row[0] if row else 0,
                "completed": (await self._get_completed_count(day_start, day_end)) or 0,
                "missed": (await self._get_missed_count(day_start, day_end)) or 0,
                "revenue": (row[1] if row else 0) or 0,
            }
    
    async def _get_completed_count(self, start: datetime, end: datetime) -> int:
        """Count completed appointments in a time range"""
        async with AsyncSessionFactory() as session:
            stmt = (
                select(func.count(Appointment.id))
                .where(
                    Appointment.clinic_id == self.clinic_id,
                    Appointment.status == "completed",
                    Appointment.scheduled_start >= start.astimezone(timezone.utc),
                    Appointment.scheduled_start < end.astimezone(timezone.utc),
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
    
    async def _get_missed_count(self, start: datetime, end: datetime) -> int:
        """Count missed appointments in a time range"""
        async with AsyncSessionFactory() as session:
            stmt = (
                select(func.count(Appointment.id))
                .where(
                    Appointment.clinic_id == self.clinic_id,
                    Appointment.status == "missed",
                    Appointment.scheduled_start >= start.astimezone(timezone.utc),
                    Appointment.scheduled_start < end.astimezone(timezone.utc),
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
    
    async def get_monthly_revenue(self, year: int, month: int) -> Dict:
        """Get revenue for a specific month"""
        first_day = datetime(year, month, 1, tzinfo=IST)
        if month == 12:
            last_day = datetime(year + 1, 1, 1, tzinfo=IST)
        else:
            last_day = datetime(year, month + 1, 1, tzinfo=IST)
        
        daily_revenues = []
        current_date = first_day
        
        while current_date < last_day:
            daily_data = await self.get_daily_revenue(current_date)
            daily_revenues.append(daily_data)
            current_date += timedelta(days=1)
        
        df = pd.DataFrame(daily_revenues)
        
        return {
            "month": first_day.strftime("%B %Y"),
            "total_revenue": int(df["revenue"].sum()),
            "total_appointments": int(df["total_appointments"].sum()),
            "completed_appointments": int(df["completed"].sum()),
            "missed_appointments": int(df["missed"].sum()),
            "no_show_rate": (
                (int(df["missed"].sum()) / int(df["total_appointments"].sum()) * 100)
                if int(df["total_appointments"].sum()) > 0
                else 0
            ),
            "daily_breakdown": daily_revenues,
        }
    
    async def get_appointment_stats(self) -> Dict:
        """Get overall appointment statistics"""
        async with AsyncSessionFactory() as session:
            stmt = (
                select(
                    Appointment.status,
                    func.count(Appointment.id).label("count"),
                )
                .where(Appointment.clinic_id == self.clinic_id)
                .group_by(Appointment.status)
            )
            
            result = await session.execute(stmt)
            rows = result.all()
            stats = {row[0]: row[1] for row in rows}
            
            return {
                "booked": stats.get("booked", 0),
                "completed": stats.get("completed", 0),
                "missed": stats.get("missed", 0),
                "total": sum(stats.values()),
            }
    
    async def get_patient_metrics(self) -> Dict:
        """Get patient-related metrics"""
        async with AsyncSessionFactory() as session:
            # Total patients
            patient_count_stmt = select(func.count(Patient.id))
            total_patients = (await session.execute(patient_count_stmt)).scalar() or 0
            
            # Returning patients
            returning_stmt = (
                select(func.count(distinct(Appointment.patient_id)))
                .where(
                    Appointment.clinic_id == self.clinic_id,
                    Appointment.status.in_(["completed", "booked"]),
                )
            )
            
            returning_patients = (await session.execute(returning_stmt)).scalar() or 0
            
            # Average appointments per patient
            avg_stmt = (
                select(func.avg(
                    select(func.count(Appointment.id))
                    .where(Appointment.patient_id == Patient.id)
                    .correlate(Patient)
                    .scalar_subquery()
                ))
            )
            
            avg_appts = (await session.execute(avg_stmt)).scalar() or 0
            
            return {
                "total_patients": total_patients,
                "returning_patients": returning_patients,
                "new_patients": max(0, total_patients - returning_patients),
                "avg_appointments_per_patient": round(float(avg_appts), 2),
            }
    
    async def get_peak_hours(self) -> List[Dict]:
        """Get busiest hours of the day"""
        async with AsyncSessionFactory() as session:
            stmt = (
                select(
                    func.extract("hour", Appointment.scheduled_start).label("hour"),
                    func.count(Appointment.id).label("count"),
                )
                .where(Appointment.clinic_id == self.clinic_id)
                .group_by(func.extract("hour", Appointment.scheduled_start))
                .order_by(func.extract("hour", Appointment.scheduled_start))
            )
            
            result = await session.execute(stmt)
            data = result.all()
            
            return [
                {
                    "hour": f"{int(hour):02d}:00",
                    "appointments": int(count),
                }
                for hour, count in data
            ]
    
    async def get_cancellation_trends(self, days: int = 30) -> Dict:
        """Get cancellation trends over last N days"""
        start_date = datetime.now(IST) - timedelta(days=days)
        
        async with AsyncSessionFactory() as session:
            stmt = (
                select(
                    func.date(Appointment.created_at).label("date"),
                    func.sum(
                        case(
                            (Appointment.status == "missed", 1),
                            else_=0,
                        )
                    ).label("cancellations"),
                    func.count(Appointment.id).label("total"),
                )
                .where(
                    Appointment.clinic_id == self.clinic_id,
                    Appointment.created_at >= start_date,
                )
                .group_by(func.date(Appointment.created_at))
                .order_by(func.date(Appointment.created_at))
            )
            
            result = await session.execute(stmt)
            data = result.all()
            
            return {
                "period_days": days,
                "data": [
                    {
                        "date": str(date),
                        "cancellations": int(cancellations),
                        "total": int(total),
                        "cancellation_rate": (
                            (cancellations / total * 100) if total > 0 else 0
                        ),
                    }
                    for date, cancellations, total in data
                ],
            }
    
    async def get_dashboard_summary(self) -> Dict:
        """Get complete dashboard summary"""
        today = datetime.now(IST)
        daily_stats = await self.get_daily_revenue(today)
        overall_stats = await self.get_appointment_stats()
        patient_metrics = await self.get_patient_metrics()
        peak_hours = await self.get_peak_hours()
        
        return {
            "today": daily_stats,
            "overall": overall_stats,
            "patients": patient_metrics,
            "peak_hours": peak_hours,
            "generated_at": datetime.now(IST).isoformat(),
        }


# Helper function for Streamlit dashboard
async def get_analytics_data(clinic_id: int = 1) -> Dict:
    """Convenience function to get all analytics data"""
    service = AnalyticsService(clinic_id)
    return await service.get_dashboard_summary()
