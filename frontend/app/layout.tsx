import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AnswerLens",
  description: "AI brand evidence and GEO readiness audits",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
