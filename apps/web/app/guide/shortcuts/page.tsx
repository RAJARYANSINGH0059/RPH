"use client";

import Shell from "@/components/Shell";
import { Section, Table } from "@/components/ui";

export default function Page() {
  return (
    <Shell title="Keyboard Shortcuts / Help" subtitle="Keys, accessibility notes and what every status chip means." pageKey="guide">
      <div className="space-y-3 max-w-3xl">
        <Section title="Keys"><Table cols={["Key", "Action"]} rows={[[<span key="k" className="kbd">Ctrl/⌘ + K</span>, "Focus the feature search in the left panel"], [<span key="k" className="kbd">?</span>, "Open the Help drawer for the current page"], [<span key="k" className="kbd">Esc</span>, "Close drawers and panels"], [<span key="k" className="kbd">Tab / Shift+Tab</span>, "Move through controls; focus rings are always visible"], [<span key="k" className="kbd">Skip to content</span>, "First focusable link on every page"]]} /></Section>
        <Section title="Accessibility"><ul className="list-disc pl-5 text-sm"><li>Every status is text + glyph + colour, never colour alone.</li><li>Motion scenes honour prefers-reduced-motion and pause off-screen; they are illustrative and carry no case data.</li><li>Graph selections are mirrored in tables so nothing depends on the canvas alone.</li><li>Collapsed navigation items keep accessible names and tooltips.</li></ul></Section>
      </div>
    </Shell>
  );
}
