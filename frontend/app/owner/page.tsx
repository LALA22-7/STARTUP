"use client";

// frontend/app/owner/page.tsx

import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  RefreshCw,
  AlertCircle,
  IndianRupee,
  CheckCircle2,
  UserX,
  Users,
  UserCheck,
  BarChart2,
} from "lucide-react";
import { getDailyAnalytics, getMonthlyAnalytics, getPatients } from "@/lib/api";
import KPICard from "@/components/KPICard";
import RevenueTrendChart from "@/components/RevenueTrendChart";

// ── Constants ─────────────────────────────────────────────────────────────────

/** Clinic ID — in a real app this would come from auth context. */
const CLINIC_ID = 1;

/** Fee per completed appointment in INR. */
const FEE_PER_APPOINTMENT = 500;

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Returns today's date in IST as { year, month, day }. */
function todayIST(): { year: number; month: number; day: number } {
  const now = new Date();
  const ist = new Date(
    now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" })
  );
  return {
    year: ist.getFullYear(),
    month: ist.getMonth() + 1, // 1-indexed
    day: ist.getDate(),
  };
}

/** Format a number as Indian rupees (e.g. 12500 → "₹12,500"). */
function formatRupees(amount: number): string {
  return `₹${amount.toLocaleString("en-IN")}`;
}

/** Format a float as a percentage string with one decimal (e.g. 12.5 → "12.5%"). */
function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

/** Returns a month label like "April 2025". */
function monthLabel(year: number, month: number): string {
  return new Date(year, month - 1, 1).toLocaleDateString("en-IN", {
    month: "long",
    year: "numeric",
  });
}

// ── MonthPicker ───────────────────────────────────────────────────────────────

interface MonthPickerProps {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
}

function MonthPicker({ year, month, onChange }: MonthPickerProps) {
  // Build a list of the last 12 months (inclusive of current)
  const options: { year: number; month: number; label: string }[] = [];
  for (let i = 0; i < 12; i++) {
    const d = new Date(year, month - 1 - i, 1);
    options.push({
      year: d.getFullYear(),
      month: d.getMonth() + 1,
      label: d.toLocaleDateString("en-IN", { month: "long", year: "numeric" }),
    });
  }

  const value = `${year}-${String(month).padStart(2, "0")}`;

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const [y, m] = e.target.value.split("-").map(Number);
    onChange(y, m);
  }

  return (
    <select
      value={value}
      onChange={handleChange}
      className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#0f8b8d]/40"
      data-testid="month-picker"
      aria-label="Select month"
    >
      {options.map((o) => (
        <option
          key={`${o.year}-${o.month}`}
          value={`${o.year}-${String(o.month).padStart(2, "0")}`}
        >
          {o.label}
        </option>
      ))}
    </select>
  );
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionHeader({
  icon: Icon,
  title,
}: {
  icon: React.ElementType;
  title: string;
}) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <Icon className="w-4 h-4 text-[#0f8b8d]" />
      <h2 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
        {title}
      </h2>
    </div>
  );
}

// ── Error banner ──────────────────────────────────────────────────────────────

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
      <AlertCircle className="w-4 h-4 flex-shrink-0" />
      {message}
    </div>
  );
}

// ── Skeleton card ─────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 flex flex-col gap-2 animate-pulse">
      <div className="h-3 w-24 bg-gray-200 rounded" />
      <div className="h-7 w-32 bg-gray-200 rounded" />
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function OwnerPage() {
  const { year: currentYear, month: currentMonth } = todayIST();
  const todayStr = new Date().toLocaleDateString("en-CA", {
    timeZone: "Asia/Kolkata",
  });

  // Selected month state (defaults to current month)
  const [selectedYear, setSelectedYear] = useState(currentYear);
  const [selectedMonth, setSelectedMonth] = useState(currentMonth);

  const handleMonthChange = useCallback((y: number, m: number) => {
    setSelectedYear(y);
    setSelectedMonth(m);
  }, []);

  // ── Queries ────────────────────────────────────────────────────────────────

  const {
    data: daily,
    isLoading: dailyLoading,
    isError: dailyError,
    refetch: refetchDaily,
  } = useQuery({
    queryKey: ["analytics", "daily", todayStr],
    queryFn: () => getDailyAnalytics(todayStr),
  });

  const {
    data: monthly,
    isLoading: monthlyLoading,
    isError: monthlyError,
    refetch: refetchMonthly,
  } = useQuery({
    queryKey: ["analytics", "monthly", selectedYear, selectedMonth],
    queryFn: () => getMonthlyAnalytics(selectedYear, selectedMonth),
  });

  const {
    data: patients = [],
    isLoading: patientsLoading,
    isError: patientsError,
    refetch: refetchPatients,
  } = useQuery({
    queryKey: ["patients", CLINIC_ID],
    queryFn: () => getPatients(CLINIC_ID),
  });

  // ── Refresh all ────────────────────────────────────────────────────────────

  const isLoading = dailyLoading || monthlyLoading || patientsLoading;

  function handleRefresh() {
    refetchDaily();
    refetchMonthly();
    refetchPatients();
  }

  // ── Derived metrics ────────────────────────────────────────────────────────

  // Today's KPIs
  const todayRevenue = daily ? daily.completed * FEE_PER_APPOINTMENT : 0;
  const todayCompleted = daily?.completed ?? 0;

  // Monthly KPIs
  const monthlyRevenue = monthly?.total_revenue ?? 0;
  const noShowRate = monthly?.no_show_rate ?? 0;

  // Patient volume
  const totalPatients = patients.length;

  // "Returning" = patients who have more than one appointment (approximated here
  // as patients registered before today — a real implementation would query
  // appointment counts per patient; we use a simple heuristic for the MVP).
  const returningPatients = patients.filter((p) => {
    const registered = new Date(p.created_at);
    const today = new Date(todayStr + "T00:00:00");
    return registered < today;
  }).length;

  // Average visits per patient — derived from monthly total appointments
  const avgVisits =
    totalPatients > 0
      ? ((monthly?.total_appointments ?? 0) / totalPatients).toFixed(1)
      : "0.0";

  // Missed analytics
  const dailyMissed = daily?.missed ?? 0;
  const monthlyMissed = monthly?.missed_appointments ?? 0;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-screen-xl mx-auto">
      {/* Page header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Owner Dashboard</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            Financial &amp; operational overview · {monthLabel(selectedYear, selectedMonth)}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <MonthPicker
            year={selectedYear}
            month={selectedMonth}
            onChange={handleMonthChange}
          />
          <button
            onClick={handleRefresh}
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
      </div>

      {/* Error banners */}
      {dailyError && (
        <ErrorBanner message="Failed to load today's analytics. Check your connection and try refreshing." />
      )}
      {monthlyError && (
        <ErrorBanner message="Failed to load monthly analytics. Check your connection and try refreshing." />
      )}
      {patientsError && (
        <ErrorBanner message="Failed to load patient data. Check your connection and try refreshing." />
      )}

      {/* ── KPI Cards ─────────────────────────────────────────────────────── */}
      <section className="mb-8" data-testid="kpi-section">
        <SectionHeader icon={IndianRupee} title="Key Metrics" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {dailyLoading || monthlyLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (
            <>
              <KPICard
                label="Today's Revenue"
                value={formatRupees(todayRevenue)}
                subLabel={`${todayCompleted} completed × ₹${FEE_PER_APPOINTMENT}`}
              />
              <KPICard
                label="Today's Completed"
                value={todayCompleted}
                subLabel={`of ${daily?.total_appointments ?? 0} total`}
              />
              <KPICard
                label="Monthly Revenue"
                value={formatRupees(monthlyRevenue)}
                subLabel={monthLabel(selectedYear, selectedMonth)}
              />
              <KPICard
                label="No-Show Rate"
                value={formatPercent(noShowRate)}
                subLabel={`${monthlyMissed} missed this month`}
              />
            </>
          )}
        </div>
      </section>

      {/* ── Patient Volume ─────────────────────────────────────────────────── */}
      <section className="mb-8" data-testid="patient-volume-section">
        <SectionHeader icon={Users} title="Patient Volume" />
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {patientsLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (
            <>
              <KPICard
                label="Total Patients"
                value={totalPatients}
                subLabel="registered"
              />
              <KPICard
                label="Returning Patients"
                value={returningPatients}
                subLabel={
                  totalPatients > 0
                    ? `${((returningPatients / totalPatients) * 100).toFixed(0)}% of total`
                    : undefined
                }
              />
              <KPICard
                label="Avg Visits / Patient"
                value={avgVisits}
                subLabel={`this month`}
              />
            </>
          )}
        </div>
      </section>

      {/* ── Revenue Trend Chart ────────────────────────────────────────────── */}
      <section className="mb-8" data-testid="revenue-chart-section">
        <SectionHeader icon={BarChart2} title="Daily Revenue Trend" />
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          {monthlyLoading ? (
            <div className="h-48 bg-gray-100 rounded-lg animate-pulse" />
          ) : (
            <RevenueTrendChart data={monthly?.daily_breakdown ?? []} />
          )}
        </div>
      </section>

      {/* ── Missed Appointment Analytics ───────────────────────────────────── */}
      <section data-testid="missed-analytics-section">
        <SectionHeader icon={UserX} title="Missed Appointment Analytics" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {dailyLoading || monthlyLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (
            <>
              <KPICard
                label="Missed Today"
                value={dailyMissed}
                subLabel={`of ${daily?.total_appointments ?? 0} scheduled`}
              />
              <KPICard
                label="Missed This Month"
                value={monthlyMissed}
                subLabel={`${formatPercent(noShowRate)} no-show rate`}
              />
            </>
          )}
        </div>
      </section>
    </div>
  );
}
