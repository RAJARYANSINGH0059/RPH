import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Playfair_Display } from "next/font/google";
import "./globals.css";

/* Display serif for titles and headline figures, a neutral grotesque for the interface, and a mono for identifiers,
 * locators and hashes. Loaded self-hosted by next/font so there is no third-party request at runtime. */
/* All three are variable fonts: the weight axis is requested whole, because pinning discrete weights breaks the
 * next/font Google loader at build time. If a face cannot be fetched the CSS stacks fall back to system faces. */
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const display = Playfair_Display({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

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
