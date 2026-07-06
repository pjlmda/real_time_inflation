import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Portugal Real-Time Inflation Tracker",
  description: "Daily grocery and fuel inflation index for Portugal, HICP-comparable.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
