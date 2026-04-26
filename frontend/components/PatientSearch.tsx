"use client";

import { useState, useEffect, useRef } from "react";
import { Search, User, Phone, Calendar, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getPatients } from "@/lib/api";
import type { Patient } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Format an ISO date string to a human-readable registration date in IST. */
function formatRegistrationDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface PatientSearchProps {
  /** Clinic ID used to scope the patient search. */
  clinicId?: number;
  /** Called when the user selects a patient from the results list. */
  onSelect: (patient: Patient) => void;
  /** Optional placeholder text for the search input. */
  placeholder?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PatientSearch({
  clinicId = 1,
  onSelect,
  placeholder = "Search by name or phone…",
}: PatientSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Patient[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // ── Debounced search ───────────────────────────────────────────────────────

  useEffect(() => {
    // Clear any pending debounce
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();

    if (!trimmed) {
      setResults([]);
      setIsOpen(false);
      setError(null);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setIsLoading(true);
      setError(null);
      try {
        const patients = await getPatients(clinicId, trimmed);
        setResults(patients);
        setIsOpen(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed");
        setResults([]);
        setIsOpen(false);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, clinicId]);

  // ── Close dropdown on outside click ───────────────────────────────────────

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // ── Handlers ───────────────────────────────────────────────────────────────

  function handleSelect(patient: Patient) {
    setQuery(patient.full_name);
    setIsOpen(false);
    setResults([]);
    onSelect(patient);
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div ref={containerRef} className="relative w-full" data-testid="patient-search">
      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          placeholder={placeholder}
          className={cn(
            "w-full pl-9 pr-10 py-2.5 rounded-xl border text-sm",
            "bg-white text-gray-900 placeholder-gray-400",
            "border-gray-200 focus:border-[#0f8b8d] focus:ring-2 focus:ring-[#0f8b8d]/20",
            "outline-none transition-colors"
          )}
          data-testid="patient-search-input"
          aria-label="Search patients"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls="patient-search-results"
          role="combobox"
        />
        {/* Loading spinner */}
        {isLoading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#0f8b8d] animate-spin" />
        )}
      </div>

      {/* Error message */}
      {error && (
        <p className="mt-1 text-xs text-red-600" data-testid="search-error">
          {error}
        </p>
      )}

      {/* Results dropdown */}
      {isOpen && results.length > 0 && (
        <ul
          id="patient-search-results"
          role="listbox"
          className={cn(
            "absolute z-50 w-full mt-1 bg-white rounded-xl border border-gray-200",
            "shadow-lg max-h-72 overflow-y-auto"
          )}
          data-testid="patient-search-results"
        >
          {results.map((patient) => (
            <li
              key={patient.id}
              role="option"
              aria-selected={false}
              onClick={() => handleSelect(patient)}
              className={cn(
                "flex items-start gap-3 px-4 py-3 cursor-pointer",
                "hover:bg-[#0f8b8d]/5 transition-colors",
                "border-b border-gray-100 last:border-b-0"
              )}
              data-testid={`patient-result-${patient.id}`}
            >
              {/* Avatar icon */}
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#0f8b8d]/10 flex items-center justify-center mt-0.5">
                <User className="w-4 h-4 text-[#0f8b8d]" />
              </div>

              {/* Patient details */}
              <div className="flex flex-col gap-0.5 min-w-0">
                <span
                  className="text-sm font-medium text-gray-900 truncate"
                  data-testid="result-name"
                >
                  {patient.full_name}
                </span>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-gray-500">
                  {patient.phone && (
                    <span className="flex items-center gap-1" data-testid="result-phone">
                      <Phone className="w-3 h-3 flex-shrink-0" />
                      {patient.phone}
                    </span>
                  )}
                  <span className="flex items-center gap-1" data-testid="result-registered">
                    <Calendar className="w-3 h-3 flex-shrink-0" />
                    Registered {formatRegistrationDate(patient.created_at)}
                  </span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* No results state */}
      {isOpen && !isLoading && results.length === 0 && query.trim() && (
        <div
          className="absolute z-50 w-full mt-1 bg-white rounded-xl border border-gray-200 shadow-lg px-4 py-3 text-sm text-gray-500"
          data-testid="no-results"
        >
          No patients found for &ldquo;{query}&rdquo;
        </div>
      )}
    </div>
  );
}
