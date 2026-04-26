// frontend/components/KPICard.tsx

import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

export interface KPICardProps {
  /** Short label shown above the value (e.g. "Today's Revenue") */
  label: string;
  /** Primary metric value displayed prominently (e.g. "₹12,500" or "24") */
  value: string | number;
  /**
   * Optional delta indicator.
   * Positive numbers render in green with an up-arrow.
   * Negative numbers render in red with a down-arrow.
   * Zero renders in gray with a dash.
   */
  delta?: number;
  /** Optional unit suffix appended to the delta (e.g. "%") */
  deltaUnit?: string;
  /** Optional sub-label shown below the value (e.g. "vs yesterday") */
  subLabel?: string;
  /** Optional additional className for the card wrapper */
  className?: string;
}

export default function KPICard({
  label,
  value,
  delta,
  deltaUnit = "",
  subLabel,
  className,
}: KPICardProps) {
  const hasDelta = delta !== undefined && delta !== null;

  const deltaColor =
    !hasDelta || delta === 0
      ? "text-gray-400"
      : delta > 0
      ? "text-green-600"
      : "text-red-500";

  const DeltaIcon =
    !hasDelta || delta === 0
      ? Minus
      : delta > 0
      ? TrendingUp
      : TrendingDown;

  const deltaLabel =
    hasDelta
      ? `${delta > 0 ? "+" : ""}${delta}${deltaUnit}`
      : null;

  return (
    <div
      className={cn(
        "bg-white rounded-xl border border-gray-200 shadow-sm p-5 flex flex-col gap-1",
        className
      )}
      data-testid="kpi-card"
    >
      {/* Label */}
      <p
        className="text-xs font-medium text-gray-500 uppercase tracking-wide"
        data-testid="kpi-label"
      >
        {label}
      </p>

      {/* Value */}
      <p
        className="text-2xl font-bold text-gray-900 leading-tight"
        data-testid="kpi-value"
      >
        {value}
      </p>

      {/* Delta + sub-label row */}
      {(hasDelta || subLabel) && (
        <div className="flex items-center gap-2 mt-1">
          {hasDelta && (
            <span
              className={cn(
                "flex items-center gap-0.5 text-xs font-medium",
                deltaColor
              )}
              data-testid="kpi-delta"
            >
              <DeltaIcon className="w-3.5 h-3.5" />
              {deltaLabel}
            </span>
          )}
          {subLabel && (
            <span className="text-xs text-gray-400" data-testid="kpi-sub-label">
              {subLabel}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
