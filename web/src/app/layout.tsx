import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradingBot | Research & Paper Trading",
  description: "A research-first futures trading workspace. Paper mode only.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
