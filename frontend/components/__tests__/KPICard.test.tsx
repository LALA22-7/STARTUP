// frontend/components/__tests__/KPICard.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import KPICard from "@/components/KPICard";

describe("KPICard", () => {
  // ── Basic rendering ────────────────────────────────────────────────────────

  it("renders the label", () => {
    render(<KPICard label="Today's Revenue" value="₹12,500" />);
    expect(screen.getByTestId("kpi-label")).toHaveTextContent("Today's Revenue");
  });

  it("renders a string value", () => {
    render(<KPICard label="Revenue" value="₹12,500" />);
    expect(screen.getByTestId("kpi-value")).toHaveTextContent("₹12,500");
  });

  it("renders a numeric value", () => {
    render(<KPICard label="Completed" value={24} />);
    expect(screen.getByTestId("kpi-value")).toHaveTextContent("24");
  });

  it("renders zero as a value", () => {
    render(<KPICard label="Missed" value={0} />);
    expect(screen.getByTestId("kpi-value")).toHaveTextContent("0");
  });

  // ── Delta indicator ────────────────────────────────────────────────────────

  it("renders a positive delta with a + prefix", () => {
    render(<KPICard label="Revenue" value="₹5,000" delta={15} deltaUnit="%" />);
    expect(screen.getByTestId("kpi-delta")).toHaveTextContent("+15%");
  });

  it("renders a negative delta without a + prefix", () => {
    render(<KPICard label="No-Show Rate" value="12%" delta={-3} deltaUnit="%" />);
    expect(screen.getByTestId("kpi-delta")).toHaveTextContent("-3%");
  });

  it("renders a zero delta", () => {
    render(<KPICard label="Revenue" value="₹0" delta={0} />);
    expect(screen.getByTestId("kpi-delta")).toHaveTextContent("0");
  });

  it("does not render delta element when delta prop is omitted", () => {
    render(<KPICard label="Revenue" value="₹5,000" />);
    expect(screen.queryByTestId("kpi-delta")).not.toBeInTheDocument();
  });

  // ── Sub-label ──────────────────────────────────────────────────────────────

  it("renders the sub-label when provided", () => {
    render(
      <KPICard label="Revenue" value="₹5,000" subLabel="vs yesterday" />
    );
    expect(screen.getByTestId("kpi-sub-label")).toHaveTextContent("vs yesterday");
  });

  it("does not render sub-label element when omitted", () => {
    render(<KPICard label="Revenue" value="₹5,000" />);
    expect(screen.queryByTestId("kpi-sub-label")).not.toBeInTheDocument();
  });

  // ── Card wrapper ───────────────────────────────────────────────────────────

  it("renders the card wrapper element", () => {
    render(<KPICard label="Revenue" value="₹5,000" />);
    expect(screen.getByTestId("kpi-card")).toBeInTheDocument();
  });
});
