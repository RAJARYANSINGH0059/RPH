import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Playfair_Display } from "next/font/google";
import "./globals.css";

/* Display serif for titles and headline figures, a neutral grotesque for the interface, and a mono for identifiers,
 * locators and hashes. Loaded self-hosted by next/font so there is no third-party request at runtime. */
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const display = Playfair_Display({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-display", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "PS05-X Investigation Workbench",
  description: "Evidence-centred financial-cybercrime investigation workbench (Rajasthan Police Hackathon 2026, PS05). Investigative aid; human verification required.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
