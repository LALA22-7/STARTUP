// frontend/components/__tests__/Sidebar.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import Sidebar from "@/components/Sidebar";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: vi.fn(),
}));

// Mock next/link to render a plain anchor
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    className,
    "data-active": dataActive,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    className?: string;
    "data-active"?: boolean;
    [key: string]: unknown;
  }) => (
    <a href={href} className={className} data-active={String(dataActive)} {...props}>
      {children}
    </a>
  ),
}));

import { usePathname } from "next/navigation";

describe("Sidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all three navigation links", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/dashboard");

    render(<Sidebar />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("EMR")).toBeInTheDocument();
  });

  it("renders the ClinicOS brand name", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/dashboard");

    render(<Sidebar />);

    expect(screen.getByText("ClinicOS")).toBeInTheDocument();
  });

  it("applies teal highlight class to the active Dashboard link", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/dashboard");

    render(<Sidebar />);

    const dashboardLink = screen.getByText("Dashboard").closest("a");
    expect(dashboardLink).toHaveClass("text-primary");
  });

  it("applies teal highlight class to the active Owner link", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/owner");

    render(<Sidebar />);

    const ownerLink = screen.getByText("Owner").closest("a");
    expect(ownerLink).toHaveClass("text-primary");
  });

  it("applies teal highlight class to the active EMR link", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/emr");

    render(<Sidebar />);

    const emrLink = screen.getByText("EMR").closest("a");
    expect(emrLink).toHaveClass("text-primary");
  });

  it("does not apply teal highlight to inactive links", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/dashboard");

    render(<Sidebar />);

    const ownerLink = screen.getByText("Owner").closest("a");
    const emrLink = screen.getByText("EMR").closest("a");

    expect(ownerLink).not.toHaveClass("text-primary");
    expect(emrLink).not.toHaveClass("text-primary");
  });

  it("marks the active link with data-active=true", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/owner");

    render(<Sidebar />);

    const ownerLink = screen.getByText("Owner").closest("a");
    expect(ownerLink).toHaveAttribute("data-active", "true");
  });

  it("marks inactive links with data-active=false", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/owner");

    render(<Sidebar />);

    const dashboardLink = screen.getByText("Dashboard").closest("a");
    expect(dashboardLink).toHaveAttribute("data-active", "false");
  });
});
