/** Warm the edge cache for every global route after a deployment.
 *
 * A fresh deployment starts with an empty CDN cache, so the first person to open each screen waits for the origin.
 * Measured on this project: a first visit took up to 11.5 s, the same visit after warming took 132 ms. Case-scoped
 * routes are skipped: they are rendered on demand and need a case id and a session, neither of which belongs here.
 *
 * Usage: node --experimental-strip-types scripts/warm-routes.mjs [base-url]
 */
import { NAV, UTILITY } from "../lib/nav.ts";

const base = (process.argv[2] || "https://rph-ps05x.vercel.app").replace(/\/$/, "");
const paths = [
  "/",
  ...NAV.flatMap((g) => g.children.filter((c) => !c.caseScoped).map((c) => c.path)),
  ...UTILITY.map((c) => c.path),
].filter((p, i, a) => p && a.indexOf(p) === i);

let slow = 0;
const results = [];
for (const p of paths) {
  const t0 = Date.now();
  try {
    const res = await fetch(base + p, { headers: { "user-agent": "ps05x-warm" } });
    const ms = Date.now() - t0;
    if (ms > 1500) slow++;
    results.push({ path: p, status: res.status, ms });
  } catch (err) {
    results.push({ path: p, status: "ERR", ms: Date.now() - t0, error: String(err) });
  }
}
const bad = results.filter((r) => r.status !== 200);
for (const r of results) console.log(`${String(r.status).padEnd(4)} ${String(r.ms).padStart(6)}ms  ${r.path}`);
console.log(`\n${results.length} routes warmed · ${bad.length} not 200 · ${slow} slower than 1.5 s`);
process.exit(bad.length ? 1 : 0);
