// frontend/components/__tests__/AppointmentCard.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AppointmentCard from "@/components/AppointmentCard";
import type { Appointment } from "@/lib/types";

// ── Mock the API module ───────────────────────────────────────────────────────
vi.mock("@/lib/api", () => ({
  patchAppointmentStatus: vi.fn(),
}));

import { patchAppointmentStatus } from "@/lib/api";

// ── Fixture ───────────────────────────────────────────────────────────────────

const BASE_APPOINTMENT: Appointment = {
  id: 42,
  clinic_id: 1,
  patient_id: 7,
  doctor_id: null,
  scheduled_start: "2025-04-26T09:30:00+05:30",
  scheduled_end: "2025-04-26T10:00:00+05:30",
  status: "booked",
  patient_name: "Priya Sharma",
  patient_phone: "+91 98765 43210",
  booking_id_display: "0042",
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AppointmentCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Rendering ──────────────────────────────────────────────────────────────

  it("renders the patient name", () => {
    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    expect(screen.getByTestId("patient-name")).toHaveTextContent("Priya Sharma");
  });

  it("renders the patient phone number", () => {
    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    expect(screen.getByTestId("patient-phone")).toHaveTextContent("+91 98765 43210");
  });

  it("renders the booking ID", () => {
    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    expect(screen.getByTestId("booking-id")).toHaveTextContent("0042");
  });

  it("renders the status badge with the correct label", () => {
    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    expect(screen.getByTestId("status-badge")).toHaveTextContent("Confirmed");
  });

  it("renders the scheduled time", () => {
    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    // Just assert the element is present — exact locale string varies by environment
    expect(screen.getByTestId("scheduled-time")).toBeInTheDocument();
  });

  it("renders Complete and Missed buttons for a booked appointment", () => {
    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    expect(screen.getByTestId("complete-button")).toBeInTheDocument();
    expect(screen.getByTestId("missed-button")).toBeInTheDocument();
  });

  it("does not render action buttons for a completed appointment", () => {
    render(
      <AppointmentCard
        appointment={{ ...BASE_APPOINTMENT, status: "completed" }}
      />
    );
    expect(screen.queryByTestId("complete-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("missed-button")).not.toBeInTheDocument();
  });

  it("does not render action buttons for a missed appointment", () => {
    render(
      <AppointmentCard
        appointment={{ ...BASE_APPOINTMENT, status: "missed" }}
      />
    );
    expect(screen.queryByTestId("complete-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("missed-button")).not.toBeInTheDocument();
  });

  it("renders the correct status badge for a waiting appointment", () => {
    render(
      <AppointmentCard
        appointment={{ ...BASE_APPOINTMENT, status: "waiting" }}
      />
    );
    expect(screen.getByTestId("status-badge")).toHaveTextContent("Waiting");
  });

  it("does not render phone row when patient_phone is null", () => {
    render(
      <AppointmentCard
        appointment={{ ...BASE_APPOINTMENT, patient_phone: null }}
      />
    );
    expect(screen.queryByTestId("patient-phone")).not.toBeInTheDocument();
  });

  // ── Status change — success path ───────────────────────────────────────────

  it("calls patchAppointmentStatus with 'completed' when Complete button is clicked", async () => {
    const updatedAppt: Appointment = { ...BASE_APPOINTMENT, status: "completed" };
    vi.mocked(patchAppointmentStatus).mockResolvedValueOnce(updatedAppt);

    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    await userEvent.click(screen.getByTestId("complete-button"));

    expect(patchAppointmentStatus).toHaveBeenCalledOnce();
    expect(patchAppointmentStatus).toHaveBeenCalledWith(42, "completed");
  });

  it("calls patchAppointmentStatus with 'missed' when Missed button is clicked", async () => {
    const updatedAppt: Appointment = { ...BASE_APPOINTMENT, status: "missed" };
    vi.mocked(patchAppointmentStatus).mockResolvedValueOnce(updatedAppt);

    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    await userEvent.click(screen.getByTestId("missed-button"));

    expect(patchAppointmentStatus).toHaveBeenCalledOnce();
    expect(patchAppointmentStatus).toHaveBeenCalledWith(42, "missed");
  });

  it("applies optimistic status update before server responds", async () => {
    // Delay the resolution so we can inspect the intermediate state
    let resolve!: (v: Appointment) => void;
    const promise = new Promise<Appointment>((res) => { resolve = res; });
    vi.mocked(patchAppointmentStatus).mockReturnValueOnce(promise);

    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);

    // Click Complete — optimistic update should fire immediately
    await userEvent.click(screen.getByTestId("complete-button"));

    // Badge should already show "Completed" before the promise resolves
    expect(screen.getByTestId("status-badge")).toHaveTextContent("Completed");

    // Resolve the promise to clean up
    resolve({ ...BASE_APPOINTMENT, status: "completed" });
    await waitFor(() =>
      expect(screen.getByTestId("status-badge")).toHaveTextContent("Completed")
    );
  });

  it("invokes onStatusChange callback with the updated appointment", async () => {
    const updatedAppt: Appointment = { ...BASE_APPOINTMENT, status: "completed" };
    vi.mocked(patchAppointmentStatus).mockResolvedValueOnce(updatedAppt);
    const onStatusChange = vi.fn();

    render(
      <AppointmentCard
        appointment={BASE_APPOINTMENT}
        onStatusChange={onStatusChange}
      />
    );
    await userEvent.click(screen.getByTestId("complete-button"));

    await waitFor(() => expect(onStatusChange).toHaveBeenCalledOnce());
    expect(onStatusChange).toHaveBeenCalledWith(updatedAppt);
  });

  // ── Status change — failure / rollback path ────────────────────────────────

  it("rolls back the optimistic update when patchAppointmentStatus rejects", async () => {
    vi.mocked(patchAppointmentStatus).mockRejectedValueOnce(
      new Error("Network error")
    );

    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);

    // Optimistic update fires immediately
    await userEvent.click(screen.getByTestId("complete-button"));

    // After rejection, status should revert to "booked" → "Confirmed"
    await waitFor(() =>
      expect(screen.getByTestId("status-badge")).toHaveTextContent("Confirmed")
    );
  });

  it("displays an error message after a failed status update", async () => {
    vi.mocked(patchAppointmentStatus).mockRejectedValueOnce(
      new Error("Server unavailable")
    );

    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    await userEvent.click(screen.getByTestId("complete-button"));

    await waitFor(() =>
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        "Server unavailable"
      )
    );
  });

  it("re-shows action buttons after rollback (status is still booked)", async () => {
    vi.mocked(patchAppointmentStatus).mockRejectedValueOnce(
      new Error("Timeout")
    );

    render(<AppointmentCard appointment={BASE_APPOINTMENT} />);
    await userEvent.click(screen.getByTestId("complete-button"));

    await waitFor(() =>
      expect(screen.getByTestId("complete-button")).toBeInTheDocument()
    );
    expect(screen.getByTestId("missed-button")).toBeInTheDocument();
  });
});
