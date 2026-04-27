"use client";

import { useState, useEffect } from "react";
import { X, Plus, Loader2 } from "lucide-react";
import { getSlots, createAppointment, createSlot, deleteSlot } from "@/lib/api";
import type { Slot } from "@/lib/api";
import type { Appointment } from "@/lib/types";

interface Props {
  clinicId: number;
  onClose: () => void;
  onCreated: (appt: Appointment) => void;
}

function formatSlotIST(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export default function AddAppointmentModal({ clinicId, onClose, onCreated }: Props) {
  const [tab, setTab] = useState<"book" | "slots">("book");

  // Book appointment form
  const [patientName, setPatientName] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [selectedSlotId, setSelectedSlotId] = useState<number | null>(null);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loadingSlots, setLoadingSlots] = useState(true);
  const [booking, setBooking] = useState(false);
  const [bookError, setBookError] = useState<string | null>(null);

  // Add slot form
  const [newSlotDate, setNewSlotDate] = useState("");
  const [newSlotStart, setNewSlotStart] = useState("");
  const [newSlotEnd, setNewSlotEnd] = useState("");
  const [addingSlot, setAddingSlot] = useState(false);
  const [slotError, setSlotError] = useState<string | null>(null);

  useEffect(() => {
    loadSlots();
  }, []);

  async function loadSlots() {
    setLoadingSlots(true);
    try {
      const data = await getSlots(clinicId);
      setSlots(data);
    } catch {
      // ignore
    } finally {
      setLoadingSlots(false);
    }
  }

  async function handleBook() {
    if (!patientName.trim() || !patientPhone.trim() || !selectedSlotId) {
      setBookError("Please fill in all fields and select a slot.");
      return;
    }
    setBooking(true);
    setBookError(null);
    try {
      const appt = await createAppointment({
        patient_name: patientName.trim(),
        patient_phone: patientPhone.trim(),
        slot_id: selectedSlotId,
        clinic_id: clinicId,
      });
      onCreated(appt);
      onClose();
    } catch (err) {
      setBookError(err instanceof Error ? err.message : "Booking failed");
    } finally {
      setBooking(false);
    }
  }

  async function handleAddSlot() {
    if (!newSlotDate || !newSlotStart || !newSlotEnd) {
      setSlotError("Please fill in date, start time, and end time.");
      return;
    }
    const start = new Date(`${newSlotDate}T${newSlotStart}:00+05:30`).toISOString();
    const end = new Date(`${newSlotDate}T${newSlotEnd}:00+05:30`).toISOString();
    if (start >= end) {
      setSlotError("End time must be after start time.");
      return;
    }
    setAddingSlot(true);
    setSlotError(null);
    try {
      await createSlot(clinicId, start, end);
      setNewSlotDate("");
      setNewSlotStart("");
      setNewSlotEnd("");
      await loadSlots();
    } catch (err) {
      setSlotError(err instanceof Error ? err.message : "Failed to add slot");
    } finally {
      setAddingSlot(false);
    }
  }

  async function handleDeleteSlot(slotId: number) {
    try {
      await deleteSlot(slotId);
      setSlots((prev) => prev.filter((s) => s.id !== slotId));
    } catch (err) {
      setSlotError(err instanceof Error ? err.message : "Failed to delete slot");
    }
  }

  const openSlots = slots.filter((s) => s.is_open);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-base font-semibold text-gray-900">Manage Appointments</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b px-6">
          {(["book", "slots"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? "border-[#0f8b8d] text-[#0f8b8d]"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "book" ? "Book Appointment" : "Manage Slots"}
            </button>
          ))}
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4">
          {/* Book Appointment Tab */}
          {tab === "book" && (
            <div className="flex flex-col gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Patient Name</label>
                <input
                  type="text"
                  value={patientName}
                  onChange={(e) => setPatientName(e.target.value)}
                  placeholder="e.g. Rahul Sharma"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#0f8b8d]"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">WhatsApp Phone</label>
                <input
                  type="text"
                  value={patientPhone}
                  onChange={(e) => setPatientPhone(e.target.value)}
                  placeholder="e.g. 919876543210"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#0f8b8d]"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Select Slot</label>
                {loadingSlots ? (
                  <p className="text-sm text-gray-400">Loading slots...</p>
                ) : openSlots.length === 0 ? (
                  <p className="text-sm text-gray-400">No open slots. Add slots in the &quot;Manage Slots&quot; tab.</p>
                ) : (
                  <div className="flex flex-col gap-2 max-h-48 overflow-y-auto">
                    {openSlots.map((slot) => (
                      <button
                        key={slot.id}
                        onClick={() => setSelectedSlotId(slot.id)}
                        className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                          selectedSlotId === slot.id
                            ? "border-[#0f8b8d] bg-teal-50 text-[#0f8b8d]"
                            : "border-gray-200 hover:border-gray-300"
                        }`}
                      >
                        {formatSlotIST(slot.slot_start)} → {formatSlotIST(slot.slot_end)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {bookError && <p className="text-xs text-red-600 bg-red-50 rounded px-3 py-2">{bookError}</p>}
              <button
                onClick={handleBook}
                disabled={booking}
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg bg-[#0f8b8d] text-white text-sm font-medium hover:bg-[#0d7a7c] disabled:opacity-50"
              >
                {booking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                {booking ? "Booking..." : "Book Appointment"}
              </button>
            </div>
          )}

          {/* Manage Slots Tab */}
          {tab === "slots" && (
            <div className="flex flex-col gap-4">
              <div className="bg-gray-50 rounded-xl p-4 flex flex-col gap-3">
                <p className="text-xs font-medium text-gray-700">Add New Slot (IST)</p>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Date</label>
                    <input
                      type="date"
                      value={newSlotDate}
                      onChange={(e) => setNewSlotDate(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#0f8b8d]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Start</label>
                    <input
                      type="time"
                      value={newSlotStart}
                      onChange={(e) => setNewSlotStart(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#0f8b8d]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">End</label>
                    <input
                      type="time"
                      value={newSlotEnd}
                      onChange={(e) => setNewSlotEnd(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#0f8b8d]"
                    />
                  </div>
                </div>
                {slotError && <p className="text-xs text-red-600">{slotError}</p>}
                <button
                  onClick={handleAddSlot}
                  disabled={addingSlot}
                  className="flex items-center justify-center gap-2 py-2 rounded-lg bg-[#0f8b8d] text-white text-xs font-medium hover:bg-[#0d7a7c] disabled:opacity-50"
                >
                  {addingSlot ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                  Add Slot
                </button>
              </div>

              {/* Slot list */}
              <div className="flex flex-col gap-2">
                <p className="text-xs font-medium text-gray-700">All Slots</p>
                {loadingSlots ? (
                  <p className="text-sm text-gray-400">Loading...</p>
                ) : slots.length === 0 ? (
                  <p className="text-sm text-gray-400">No slots yet.</p>
                ) : (
                  slots.map((slot) => (
                    <div
                      key={slot.id}
                      className="flex items-center justify-between px-3 py-2 rounded-lg border border-gray-200 text-sm"
                    >
                      <span className="text-gray-700">
                        {formatSlotIST(slot.slot_start)}
                        <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${slot.is_open ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                          {slot.is_open ? "Open" : "Booked"}
                        </span>
                      </span>
                      {slot.is_open && (
                        <button
                          onClick={() => handleDeleteSlot(slot.id)}
                          className="text-gray-400 hover:text-red-500 transition-colors"
                          title="Delete slot"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
