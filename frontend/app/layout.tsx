import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import QueryProvider from "@/components/QueryProvider";

export const metadata: Metadata = {
  title: "ClinicOS",
  description: "WhatsApp-first SaaS platform for Indian clinics",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex min-h-screen bg-gray-50">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <QueryProvider>{children}</QueryProvider>
        </main>
      </body>
    </html>
  );
}
