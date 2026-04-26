// frontend/lib/types.ts

export type AppointmentStatus = "booked" | "completed" | "missed" | "waiting";

export interface Appointment {
  id: number;
  clinic_id: number;
  patient_id: number;
  doctor_id: number | null;
  scheduled_start: string; // ISO 8601
  scheduled_end: string;
  status: AppointmentStatus;
  patient_name: string;
  patient_phone: string | null;
  booking_id_display: string;
}

export interface AppointmentQueryParams {
  clinic_id: number;
  status?: AppointmentStatus;
  date_from?: string; // ISO date string
  date_to?: string; // ISO date string
}

export interface DailyAnalytics {
  date: string;
  total_appointments: number;
  completed: number;
  missed: number;
  revenue: number;
}

export interface MonthlyAnalytics {
  month: string;
  total_revenue: number;
  total_appointments: number;
  completed_appointments: number;
  missed_appointments: number;
  no_show_rate: number;
  daily_breakdown: DailyAnalytics[];
}

export interface Patient {
  id: number;
  full_name: string;
  phone: string | null;
  email: string;
  created_at: string; // ISO 8601
}

export interface Encounter {
  id: number;
  patient_id: number;
  record: Record<string, unknown>;
  created_at: string; // ISO 8601
}
