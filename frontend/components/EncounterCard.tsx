"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Clock, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Encounter } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Format an ISO datetime string to a human-readable IST timestamp. */
function formatIST(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

/**
 * Render a record value as a human-readable string.
 * Objects and arrays are pretty-printed as JSON; primitives are cast to string.
 */
function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

/**
 * Priority fields to display first when the record is expanded.
 * Any remaining keys are shown after these in alphabetical order.
 */
const PRIORITY_FIELDS = ["summary", "source", "diagnosis", "symptoms", "treatment", "notes"];

function sortedRecordEntries(
  record: Record<string, unknown>
): [string, unknown][] {
  const entries = Object.entries(record);
  const priority = entries.filter(([k]) => PRIORITY_FIELDS.includes(k));
  const rest = entries
    .filter(([k]) => !PRIORITY_FIELDS.includes(k))
    .sort(([a], [b]) => a.localeCompare(b));
  return [...priority, ...rest];
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface EncounterCardProps {
  encounter: Encounter;
  /** If true, the card starts in the expanded state. */
  defaultExpanded?: boolean;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function EncounterCard({
  encounter,
  defaultExpanded = false,
}: EncounterCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const sortedEntries = sortedRecordEntries(encounter.record);

  return (
    <div
      className={cn(
        "bg-white rounded-xl border border-gray-200 shadow-sm transition-shadow",
        isExpanded ? "shadow-md" : "hover:shadow-md"
      )}
      data-testid="encounter-card"
    >
      {/* ── Collapsed header (always visible) ─────────────────────────────── */}
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className={cn(
          "w-full flex items-center gap-3 px-4 py-3 text-left",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0f8b8d]/50 rounded-xl",
          isExpanded && "border-b border-gray-100"
        )}
        aria-expanded={isExpanded}
        data-testid="encounter-toggle"
      >
        {/* Icon */}
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#0f8b8d]/10 flex items-center justify-center">
          <FileText className="w-4 h-4 text-[#0f8b8d]" />
        </div>

        {/* Timestamp */}
        <div className="flex-1 min-w-0">
          <span
            className="flex items-center gap-1.5 text-sm font-medium text-gray-900"
            data-testid="encounter-timestamp"
          >
            <Clock className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
            {formatIST(encounter.created_at)}
          </span>
          {/* Show summary preview when collapsed */}
          {!isExpanded && !!encounter.record.summary && (
            <p className="mt-0.5 text-xs text-gray-500 truncate">
              {String(encounter.record.summary)}
            </p>
          )}
        </div>

        {/* Expand/collapse chevron */}
        <div className="flex-shrink-0 text-gray-400">
          {isExpanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </div>
      </button>

      {/* ── Expanded body ──────────────────────────────────────────────────── */}
      {isExpanded && (
        <div className="px-4 py-4" data-testid="encounter-body">
          {sortedEntries.length === 0 ? (
            <p className="text-sm text-gray-400 italic">No record data available.</p>
          ) : (
            <dl className="flex flex-col gap-3">
              {sortedEntries.map(([key, value]) => {
                const isMultiline =
                  typeof value === "object" && value !== null;
                return (
                  <div key={key} className="flex flex-col gap-0.5">
                    {/* Field label */}
                    <dt className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      {key.replace(/_/g, " ")}
                    </dt>
                    {/* Field value */}
                    <dd
                      className={cn(
                        "text-sm text-gray-800",
                        isMultiline &&
                          "font-mono bg-gray-50 rounded-lg px-3 py-2 text-xs whitespace-pre-wrap border border-gray-100"
                      )}
                      data-testid={`encounter-field-${key}`}
                    >
                      {renderValue(value)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
