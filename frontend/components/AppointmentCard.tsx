"use client";

import { useState } from "react";
import { Phone, Clock, Hash, CheckCircle, XCircle, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { patchAppointmentStatus, deleteAppointment } from "@/lib/api";
import type { Appointment, AppointmentStatus } from "@/lib/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Format an ISO 8601 datetime string to a human-readable IST time. */
function formatIST(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

// ── Status badge ─────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<AppointmentStatus, string> = {
  booked: "bg-blue-100 text-blue-700 border-blue-200",
  waiting: "bg-yellow-100 text-yellow-700 border-yellow-200",
  completed: "bg-green-100 text-green-700 border-green-200",
  missed: "bg-red-100 text-red-700 border-red-200",
};

const STATUS_LABELS: Record<AppointmentStatus, string> = {
  booked: "Confirmed",
  waiting: "Waiting",
  completed: "Completed",
  missed: "Missed",
};

function StatusBadge({ status }: { status: AppointmentStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border",
        STATUS_STYLES[status]
      )}
      data-testid="status-badge"
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface AppointmentCardProps {
  appointment: Appointment;
  onStatusChange?: (updated: Appointment) => void;
  onDelete?: (id: number) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function AppointmentCard({
  appointment,
  onStatusChange,
  onDelete,
}: AppointmentCardProps) {
  const [localAppt, setLocalAppt] = useState<Appointment>(appointment);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStatusChange(newStatus: AppointmentStatus) {
    if (isUpdating) return;
    const previous = localAppt;
    setLocalAppt((prev) => ({ ...prev, status: newStatus }));
    setIsUpdating(true);
    setError(null);
    try {
      const updated = await patchAppointmentStatus(localAppt.id, newStatus);
      setLocalAppt(updated);
      onStatusChange?.(updated);
    } catch (err) {
      setLocalAppt(previous);
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setIsUpdating(false);
    }
  }

  async function handleDelete() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setIsDeleting(true);
    try {
      await deleteAppointment(localAppt.id);
      onDelete?.(localAppt.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setIsDeleting(false);
      setConfirmDelete(false);
    }
  }

  const isBooked = localAppt.status === "booked";

  return (
    <div
      className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex flex-col gap-3 hover:shadow-md transition-shadow"
      data-testid="appointment-card"
    >
      {/* Header row: patient name + status badge */}
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold text-gray-900 text-sm leading-tight" data-testid="patient-name">
          {localAppt.patient_name}
        </p>
        <StatusBadge status={localAppt.status} />
      </div>

      {/* Detail rows */}
      <div className="flex flex-col gap-1.5 text-xs text-gray-500">
        {localAppt.patient_phone && (
          <span className="flex items-center gap-1.5" data-testid="patient-phone">
            <Phone className="w-3.5 h-3.5 flex-shrink-0" />
            {localAppt.patient_phone}
          </span>
        )}
        <span className="flex items-center gap-1.5" data-testid="scheduled-time">
          <Clock className="w-3.5 h-3.5 flex-shrink-0" />
          {formatIST(localAppt.scheduled_start)}
        </span>
        <span className="flex items-center gap-1.5" data-testid="booking-id">
          <Hash className="w-3.5 h-3.5 flex-shrink-0" />
          Booking #{localAppt.booking_id_display}
        </span>
      </div>

      {/* Error message */}
      {error && (
        <p className="text-xs text-red-600 bg-red-50 rounded px-2 py-1" data-testid="error-message">
          {error}
        </p>
      )}

      {/* Action buttons */}
      {isBooked && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => handleStatusChange("completed")}
            disabled={isUpdating}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
              "bg-green-50 text-green-700 border border-green-200 hover:bg-green-100",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
            data-testid="complete-button"
          >
            <CheckCircle className="w-3.5 h-3.5" />
            Complete
          </button>
          <button
            onClick={() => handleStatusChange("missed")}
            disabled={isUpdating}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
              "bg-red-50 text-red-700 border border-red-200 hover:bg-red-100",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
            data-testid="missed-button"
          >
            <XCircle className="w-3.5 h-3.5" />
            Missed
          </button>
        </div>
      )}

      {/* Delete button */}
      <button
        onClick={handleDelete}
        disabled={isDeleting}
        className={cn(
          "flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors w-full",
          confirmDelete
            ? "bg-red-600 text-white hover:bg-red-700"
            : "bg-gray-50 text-gray-500 border border-gray-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
        data-testid="delete-button"
      >
        <Trash2 className="w-3.5 h-3.5" />
        {confirmDelete ? "Confirm Delete" : "Delete"}
      </button>
      {confirmDelete && (
        <button
          onClick={() => setConfirmDelete(false)}
          className="text-xs text-gray-400 hover:text-gray-600 text-center"
        >
          Cancel
        </button>
      )}
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Format an ISO 8601 datetime string to a human-readable IST time. */
function formatIST(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

// ── Status badge ─────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<AppointmentStatus, string> = {
  booked: "bg-blue-100 text-blue-700 border-blue-200",
  waiting: "bg-yellow-100 text-yellow-700 border-yellow-200",
  completed: "bg-green-100 text-green-700 border-green-200",
  missed: "bg-red-100 text-red-700 border-red-200",
};

const STATUS_LABELS: Record<AppointmentStatus, string> = {
  booked: "Confirmed",
  waiting: "Waiting",
  completed: "Completed",
  missed: "Missed",
};

function StatusBadge({ status }: { status: AppointmentStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border",
        STATUS_STYLES[status]
      )}
      data-testid="status-badge"
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface AppointmentCardProps {
  appointment: Appointment;
  /** Called after a successful status update so the parent can refresh its list. */
  onStatusChange?: (updated: Appointment) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function AppointmentCard({
  appointment,
  onStatusChange,
}: AppointmentCardProps) {
  // Optimistic local state — starts from the server value.
  const [localAppt, setLocalAppt] = useState<Appointment>(appointment);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStatusChange(newStatus: AppointmentStatus) {
    if (isUpdating) return;

    // Optimistic update
    const previous = localAppt;
    setLocalAppt((prev) => ({ ...prev, status: newStatus }));
    setIsUpdating(true);
    setError(null);

    try {
      const updated = await patchAppointmentStatus(localAppt.id, newStatus);
      setLocalAppt(updated);
      onStatusChange?.(updated);
    } catch (err) {
      // Rollback on failure
      setLocalAppt(previous);
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setIsUpdating(false);
    }
  }

  const isBooked = localAppt.status === "booked";

  return (
    <div
      className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex flex-col gap-3 hover:shadow-md transition-shadow"
      data-testid="appointment-card"
    >
      {/* Header row: patient name + status badge */}
      <div className="flex items-start justify-between gap-2">
        <p
          className="font-semibold text-gray-900 text-sm leading-tight"
          data-testid="patient-name"
        >
          {localAppt.patient_name}
        </p>
        <StatusBadge status={localAppt.status} />
      </div>

      {/* Detail rows */}
      <div className="flex flex-col gap-1.5 text-xs text-gray-500">
        {localAppt.patient_phone && (
          <span className="flex items-center gap-1.5" data-testid="patient-phone">
            <Phone className="w-3.5 h-3.5 flex-shrink-0" />
            {localAppt.patient_phone}
          </span>
        )}
        <span className="flex items-center gap-1.5" data-testid="scheduled-time">
          <Clock className="w-3.5 h-3.5 flex-shrink-0" />
          {formatIST(localAppt.scheduled_start)}
        </span>
        <span className="flex items-center gap-1.5" data-testid="booking-id">
          <Hash className="w-3.5 h-3.5 flex-shrink-0" />
          Booking #{localAppt.booking_id_display}
        </span>
      </div>

      {/* Error message */}
      {error && (
        <p className="text-xs text-red-600 bg-red-50 rounded px-2 py-1" data-testid="error-message">
          {error}
        </p>
      )}

      {/* Action buttons — only shown for "booked" (Confirmed) appointments */}
      {isBooked && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => handleStatusChange("completed")}
            disabled={isUpdating}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
              "bg-green-50 text-green-700 border border-green-200 hover:bg-green-100",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
            data-testid="complete-button"
          >
            <CheckCircle className="w-3.5 h-3.5" />
            Complete
          </button>
          <button
            onClick={() => handleStatusChange("missed")}
            disabled={isUpdating}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
              "bg-red-50 text-red-700 border border-red-200 hover:bg-red-100",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
            data-testid="missed-button"
          >
            <XCircle className="w-3.5 h-3.5" />
            Missed
          </button>
        </div>
      )}
    </div>
  );
}
