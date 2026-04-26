"use client";

import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Calendar, Clock, AlertCircle } from "lucide-react";
import { getAppointments } from "@/lib/api";
import AppointmentCard from "@/components/AppointmentCard";
import type { Appointment } from "@/lib/types";

// ── Constants ─────────────────────────────────────────────────────────────────

/** Clinic ID — in a real app this would come from auth context or URL params. */
const CLINIC_ID = 1;

/** Polling interval: 30 seconds */
const REFETCH_INTERVAL = 30_000;

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Returns the current date in IST as a "YYYY-MM-DD" string. */
function todayIST(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

/** Returns an ISO datetime string for now + 24 hours. */
function in24Hours(): Date {
  return new Date(Date.now() + 24 * 60 * 60 * 1000);
}

/** Parses an ISO string and returns a Date. */
function parseDate(iso: string): Date {
  return new Date(iso);
}

/** Returns the date portion of an ISO string in IST ("YYYY-MM-DD"). */
function dateInIST(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", {
    timeZone: "Asia/Kolkata",
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({
  icon: Icon,
  title,
  count,
}: {
  icon: React.ElementType;
  title: string;
  count: number;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-4 h-4 text-[#0f8b8d]" />
      <h2 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
        {title}
      </h2>
      <span className="ml-auto bg-gray-100 text-gray-600 text-xs font-medium px-2 py-0.5 rounded-full">
        {count}
      </span>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-24 rounded-xl border border-dashed border-gray-200 text-gray-400 text-sm">
      {message}
    </div>
  );
}

function AppointmentColumn({
  title,
  icon,
  appointments,
  onStatusChange,
  emptyMessage,
}: {
  title: string;
  icon: React.ElementType;
  appointments: Appointment[];
  onStatusChange: (updated: Appointment) => void;
  emptyMessage: string;
}) {
  return (
    <div className="flex flex-col min-w-0">
      <SectionHeader icon={icon} title={title} count={appointments.length} />
      <div className="flex flex-col gap-3">
        {appointments.length === 0 ? (
          <EmptyState message={emptyMessage} />
        ) : (
          appointments.map((appt) => (
            <AppointmentCard
              key={appt.id}
              appointment={appt}
              onStatusChange={onStatusChange}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const queryClient = useQueryClient();

  const {
    data: appointments = [],
    isLoading,
    isError,
    dataUpdatedAt,
    refetch,
  } = useQuery({
    queryKey: ["appointments", CLINIC_ID],
    queryFn: () => getAppointments({ clinic_id: CLINIC_ID }),
    refetchInterval: REFETCH_INTERVAL,
  });

  // Optimistically update the cached list when a card reports a status change.
  const handleStatusChange = useCallback(
    (updated: Appointment) => {
      queryClient.setQueryData<Appointment[]>(
        ["appointments", CLINIC_ID],
        (prev = []) =>
          prev.map((a) => (a.id === updated.id ? updated : a))
      );
    },
    [queryClient]
  );

  // ── Derived lists ──────────────────────────────────────────────────────────

  const confirmed = useMemo(
    () => appointments.filter((a) => a.status === "booked"),
    [appointments]
  );

  const waiting = useMemo(
    () => appointments.filter((a) => a.status === "waiting"),
    [appointments]
  );

  const completed = useMemo(
    () => appointments.filter((a) => a.status === "completed"),
    [appointments]
  );

  const upcoming = useMemo(() => {
    const now = new Date();
    const cutoff = in24Hours();
    return appointments
      .filter((a) => {
        const start = parseDate(a.scheduled_start);
        return start >= now && start <= cutoff;
      })
      .sort(
        (a, b) =>
          parseDate(a.scheduled_start).getTime() -
          parseDate(b.scheduled_start).getTime()
      );
  }, [appointments]);

  const missed = useMemo(() => {
    const today = todayIST();
    return appointments.filter(
      (a) => a.status === "missed" && dateInIST(a.scheduled_start) === today
    );
  }, [appointments]);

  // ── Last-updated label ─────────────────────────────────────────────────────

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString("en-IN", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      })
    : null;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-screen-xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            Appointment Control Center
          </h1>
          {lastUpdated && (
            <p className="text-xs text-gray-400 mt-0.5">
              Last updated at {lastUpdated} IST · auto-refreshes every 30 s
            </p>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-[#0f8b8d] text-white hover:bg-[#0d7a7c] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          data-testid="refresh-button"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`}
          />
          Refresh
        </button>
      </div>

      {/* Error banner */}
      {isError && (
        <div className="flex items-center gap-2 mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          Failed to load appointments. Check your connection and try refreshing.
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex flex-col gap-3">
              <div className="h-5 w-32 bg-gray-200 rounded animate-pulse" />
              {[0, 1].map((j) => (
                <div
                  key={j}
                  className="h-28 bg-gray-100 rounded-xl animate-pulse"
                />
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Three-column queue */}
      {!isLoading && (
        <>
          <div
            className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
            data-testid="appointment-columns"
          >
            <AppointmentColumn
              title="Confirmed"
              icon={Calendar}
              appointments={confirmed}
              onStatusChange={handleStatusChange}
              emptyMessage="No confirmed appointments"
            />
            <AppointmentColumn
              title="Waiting"
              icon={Clock}
              appointments={waiting}
              onStatusChange={handleStatusChange}
              emptyMessage="No patients waiting"
            />
            <AppointmentColumn
              title="Completed"
              icon={Calendar}
              appointments={completed}
              onStatusChange={handleStatusChange}
              emptyMessage="No completed appointments"
            />
          </div>

          {/* Upcoming section — next 24 hours */}
          <section className="mb-8" data-testid="upcoming-section">
            <SectionHeader
              icon={Clock}
              title="Upcoming (next 24 hours)"
              count={upcoming.length}
            />
            {upcoming.length === 0 ? (
              <EmptyState message="No upcoming appointments in the next 24 hours" />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {upcoming.map((appt) => (
                  <AppointmentCard
                    key={appt.id}
                    appointment={appt}
                    onStatusChange={handleStatusChange}
                  />
                ))}
              </div>
            )}
          </section>

          {/* Missed section — today in IST */}
          <section data-testid="missed-section">
            <SectionHeader
              icon={AlertCircle}
              title="Missed Today"
              count={missed.length}
            />
            {missed.length === 0 ? (
              <EmptyState message="No missed appointments today" />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {missed.map((appt) => (
                  <AppointmentCard
                    key={appt.id}
                    appointment={appt}
                    onStatusChange={handleStatusChange}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
