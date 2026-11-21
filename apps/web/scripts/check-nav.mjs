// Navigation registry test: every destination exactly once, every case-scoped path has a page file, no duplicate keys.
// Run: node --experimental-strip-types scripts/check-nav.mjs   (Node 22+)
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { NAV, UTILITY, allChildren, duplicateDestinations, hrefFor } from "../lib/nav.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "app");
let failures = 0;
const dups = duplicateDestinations();
if (dups.length) { console.error("duplicate destinations:", dups); failures++; }
const keys = allChildren().map((x) => x.child.key);
const dupKeys = keys.filter((k, i) => keys.indexOf(k) !== i);
if (dupKeys.length) { console.error("duplicate keys:", dupKeys); failures++; }
for (const { child } of allChildren()) {
  const href = hrefFor(child, "00000000-0000-0000-0000-000000000000").split("?")[0];
  const rel = href.replace(/^\/cases\/[0-9a-f-]{36}/, "/cases/[id]");
  const page = join(root, rel === "/" ? "" : rel, "page.tsx");
  if (!existsSync(page)) { console.error("missing page for", child.label, "->", rel); failures++; }
}
console.log(`${NAV.length} groups, ${allChildren().length - UTILITY.length} feature routes, ${UTILITY.length} utility routes, ${failures} problem(s)`);
process.exit(failures ? 1 : 0);
