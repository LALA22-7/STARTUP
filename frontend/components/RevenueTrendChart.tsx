"use client";

// frontend/components/RevenueTrendChart.tsx

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { DailyAnalytics } from "@/lib/types";

export interface RevenueTrendChartProps {
  /** Daily analytics array — one entry per day. Safe to pass an empty array. */
  data: DailyAnalytics[];
}

/** Format a "YYYY-MM-DD" date string to a short day label like "Apr 1". */
function formatDay(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
}

/** Format a rupee amount for the Y-axis tick (e.g. 12500 → "₹12.5k"). */
function formatRevenueTick(value: number): string {
  if (value >= 1000) return `₹${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`;
  return `₹${value}`;
}

/** Custom tooltip shown on hover. */
function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-md px-3 py-2 text-sm">
      <p className="font-medium text-gray-700">{label}</p>
      <p className="text-[#0f8b8d] font-semibold">
        ₹{payload[0].value.toLocaleString("en-IN")}
      </p>
    </div>
  );
}

export default function RevenueTrendChart({ data }: RevenueTrendChartProps) {
  // Map to chart-friendly shape
  const chartData = data.map((d) => ({
    day: formatDay(d.date),
    revenue: d.revenue,
  }));

  if (chartData.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-48 rounded-xl border border-dashed border-gray-200 text-gray-400 text-sm"
        data-testid="revenue-chart-empty"
      >
        No revenue data for this period
      </div>
    );
  }

  return (
    <div data-testid="revenue-chart" className="w-full h-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={chartData}
          margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="day"
            tick={{ fontSize: 11, fill: "#9ca3af" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tickFormatter={formatRevenueTick}
            tick={{ fontSize: 11, fill: "#9ca3af" }}
            tickLine={false}
            axisLine={false}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="revenue"
            stroke="#0f8b8d"
            strokeWidth={2}
            dot={{ r: 3, fill: "#0f8b8d", strokeWidth: 0 }}
            activeDot={{ r: 5, fill: "#0f8b8d" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
