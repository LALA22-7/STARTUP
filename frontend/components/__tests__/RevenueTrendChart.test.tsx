// frontend/components/__tests__/RevenueTrendChart.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import RevenueTrendChart from "@/components/RevenueTrendChart";
import type { DailyAnalytics } from "@/lib/types";

// ── Recharts mock ─────────────────────────────────────────────────────────────
// Recharts uses ResizeObserver and SVG APIs not available in jsdom.
// We replace the heavy chart primitives with lightweight stubs so the
// component tree renders without errors.
vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SAMPLE_DATA: DailyAnalytics[] = [
  { date: "2025-04-01", total_appointments: 10, completed: 8, missed: 2, revenue: 4000 },
  { date: "2025-04-02", total_appointments: 12, completed: 10, missed: 2, revenue: 5000 },
  { date: "2025-04-03", total_appointments: 8,  completed: 7,  missed: 1, revenue: 3500 },
];

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RevenueTrendChart", () => {
  // ── Empty data ─────────────────────────────────────────────────────────────

  it("renders without crashing when data is an empty array", () => {
    expect(() => render(<RevenueTrendChart data={[]} />)).not.toThrow();
  });

  it("shows an empty-state message when data is empty", () => {
    render(<RevenueTrendChart data={[]} />);
    expect(screen.getByTestId("revenue-chart-empty")).toBeInTheDocument();
  });

  it("does not render the chart when data is empty", () => {
    render(<RevenueTrendChart data={[]} />);
    expect(screen.queryByTestId("revenue-chart")).not.toBeInTheDocument();
  });

  // ── With data ──────────────────────────────────────────────────────────────

  it("renders without crashing when data has entries", () => {
    expect(() => render(<RevenueTrendChart data={SAMPLE_DATA} />)).not.toThrow();
  });

  it("renders the chart container when data is provided", () => {
    render(<RevenueTrendChart data={SAMPLE_DATA} />);
    expect(screen.getByTestId("revenue-chart")).toBeInTheDocument();
  });

  it("renders the ResponsiveContainer when data is provided", () => {
    render(<RevenueTrendChart data={SAMPLE_DATA} />);
    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
  });

  it("renders the LineChart when data is provided", () => {
    render(<RevenueTrendChart data={SAMPLE_DATA} />);
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  it("does not show the empty-state message when data is provided", () => {
    render(<RevenueTrendChart data={SAMPLE_DATA} />);
    expect(screen.queryByTestId("revenue-chart-empty")).not.toBeInTheDocument();
  });

  // ── Single data point ──────────────────────────────────────────────────────

  it("renders without crashing for a single data point", () => {
    const single: DailyAnalytics[] = [
      { date: "2025-04-01", total_appointments: 5, completed: 4, missed: 1, revenue: 2000 },
    ];
    expect(() => render(<RevenueTrendChart data={single} />)).not.toThrow();
  });
});
