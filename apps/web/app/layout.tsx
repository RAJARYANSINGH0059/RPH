import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PS05-X Investigation Workbench",
  description: "Evidence-centred financial-cybercrime investigation workbench (Rajasthan Police Hackathon 2026, PS05). Investigative aid; human verification required.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
