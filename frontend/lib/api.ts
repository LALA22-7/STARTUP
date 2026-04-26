// frontend/lib/api.ts

import type {
  Appointment,
  AppointmentQueryParams,
  AppointmentStatus,
  DailyAnalytics,
  MonthlyAnalytics,
  Patient,
  Encounter,
} from "@/lib/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function getAppointments(
  params: AppointmentQueryParams
): Promise<Appointment[]> {
  const query = new URLSearchParams();
  query.set("clinic_id", String(params.clinic_id));
  if (params.status) query.set("status", params.status);
  if (params.date_from) query.set("date_from", params.date_from);
  if (params.date_to) query.set("date_to", params.date_to);
  return apiFetch<Appointment[]>(`/api/appointments?${query.toString()}`);
}

export async function patchAppointmentStatus(
  id: number,
  status: AppointmentStatus
): Promise<Appointment> {
  return apiFetch<Appointment>(`/api/appointments/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function getDailyAnalytics(date?: string): Promise<DailyAnalytics> {
  const query = date ? `?date=${date}` : "";
  return apiFetch<DailyAnalytics>(`/api/analytics/daily${query}`);
}

export async function getMonthlyAnalytics(
  year: number,
  month: number
): Promise<MonthlyAnalytics> {
  return apiFetch<MonthlyAnalytics>(
    `/api/analytics/monthly?year=${year}&month=${month}`
  );
}

export async function getPatients(
  clinicId: number,
  search?: string
): Promise<Patient[]> {
  const query = new URLSearchParams();
  query.set("clinic_id", String(clinicId));
  if (search) query.set("search", search);
  return apiFetch<Patient[]>(`/api/patients?${query.toString()}`);
}

export async function getPatientEncounters(
  patientId: number
): Promise<Encounter[]> {
  return apiFetch<Encounter[]>(`/api/patients/${patientId}/encounters`);
}
