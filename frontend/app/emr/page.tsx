"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { User, Phone, Calendar, FileText, AlertCircle, Loader2 } from "lucide-react";
import PatientSearch from "@/components/PatientSearch";
import EncounterCard from "@/components/EncounterCard";
import { getPatientEncounters } from "@/lib/api";
import type { Patient } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Format an ISO date string to a human-readable date in IST. */
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PatientHeader({ patient }: { patient: Patient }) {
  return (
    <div
      className="flex items-center gap-4 p-4 bg-white rounded-xl border border-gray-200 shadow-sm"
      data-testid="patient-header"
    >
      {/* Avatar */}
      <div className="flex-shrink-0 w-12 h-12 rounded-full bg-[#0f8b8d]/10 flex items-center justify-center">
        <User className="w-6 h-6 text-[#0f8b8d]" />
      </div>

      {/* Details */}
      <div className="flex flex-col gap-1 min-w-0">
        <h2
          className="text-base font-semibold text-gray-900 truncate"
          data-testid="patient-header-name"
        >
          {patient.full_name}
        </h2>
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-gray-500">
          {patient.phone && (
            <span className="flex items-center gap-1" data-testid="patient-header-phone">
              <Phone className="w-3 h-3 flex-shrink-0" />
              {patient.phone}
            </span>
          )}
          <span className="flex items-center gap-1" data-testid="patient-header-registered">
            <Calendar className="w-3 h-3 flex-shrink-0" />
            Registered {formatDate(patient.created_at)}
          </span>
        </div>
      </div>
    </div>
  );
}

function EmptyEncounters() {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 py-16 text-center"
      data-testid="no-encounters"
    >
      <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center">
        <FileText className="w-6 h-6 text-gray-400" />
      </div>
      <p className="text-sm font-medium text-gray-500">No clinical records found</p>
      <p className="text-xs text-gray-400">
        Encounters will appear here once clinical notes are recorded.
      </p>
    </div>
  );
}

function SelectPatientPrompt() {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 py-20 text-center"
      data-testid="select-patient-prompt"
    >
      <div className="w-14 h-14 rounded-full bg-[#0f8b8d]/10 flex items-center justify-center">
        <User className="w-7 h-7 text-[#0f8b8d]" />
      </div>
      <p className="text-sm font-medium text-gray-600">
        Search for a patient to view their clinical history
      </p>
      <p className="text-xs text-gray-400">
        Use the search box above to find a patient by name or phone number.
      </p>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function EMRPage() {
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);

  const {
    data: encounters = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["encounters", selectedPatient?.id],
    queryFn: () => getPatientEncounters(selectedPatient!.id),
    enabled: selectedPatient !== null,
  });

  function handlePatientSelect(patient: Patient) {
    // If a different patient is selected, clear the previous encounters view
    if (selectedPatient?.id !== patient.id) {
      setSelectedPatient(patient);
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto" data-testid="emr-page">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Patient Records</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Search for a patient to view their clinical encounter history.
        </p>
      </div>

      {/* Patient search */}
      <div className="mb-6">
        <PatientSearch onSelect={handlePatientSelect} />
      </div>

      {/* Patient header — shown once a patient is selected */}
      {selectedPatient && (
        <div className="mb-6">
          <PatientHeader patient={selectedPatient} />
        </div>
      )}

      {/* Encounter list area */}
      {!selectedPatient ? (
        <SelectPatientPrompt />
      ) : isLoading ? (
        <div
          className="flex items-center justify-center gap-2 py-16 text-gray-500 text-sm"
          data-testid="encounters-loading"
        >
          <Loader2 className="w-4 h-4 animate-spin text-[#0f8b8d]" />
          Loading clinical records…
        </div>
      ) : isError ? (
        <div
          className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm"
          data-testid="encounters-error"
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error instanceof Error
            ? error.message
            : "Failed to load clinical records. Please try again."}
        </div>
      ) : encounters.length === 0 ? (
        <EmptyEncounters />
      ) : (
        <section data-testid="encounter-list">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="w-4 h-4 text-[#0f8b8d]" />
            <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
              Clinical Encounters
            </h3>
            <span className="ml-auto bg-gray-100 text-gray-600 text-xs font-medium px-2 py-0.5 rounded-full">
              {encounters.length}
            </span>
          </div>
          <div className="flex flex-col gap-3">
            {encounters.map((encounter) => (
              <EncounterCard key={encounter.id} encounter={encounter} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
