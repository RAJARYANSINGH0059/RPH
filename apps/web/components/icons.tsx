import type { SVGProps } from "react";

const base = (p: SVGProps<SVGSVGElement>) => ({ width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true, ...p });

export const I = {
  cases: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 7h5l2 2h11v10H3z" /><path d="M3 7V5h6" /></svg>,
  upload: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 16V4m0 0l-4 4m4-4l4 4" /><path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" /></svg>,
  graph: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="5" cy="6" r="2.5" /><circle cx="19" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M7 7.5l3.5 8M17 7.5l-3.5 8M7.5 6h9" /></svg>,
  timeline: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 12h16" /><circle cx="7" cy="12" r="2" /><circle cx="14" cy="12" r="2" /><circle cx="20" cy="12" r="1.5" /><path d="M7 10V6m7 8v4" /></svg>,
  report: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 13h6M9 17h6M9 9h2" /></svg>,
  sources: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6" /><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" /></svg>,
  factory: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9L9.5 8z" /></svg>,
  money: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><rect x="3" y="6" width="18" height="12" rx="2" /><circle cx="12" cy="12" r="2.5" /><path d="M7 12h.01M17 12h.01" /></svg>,
  help: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 015 0c0 1.5-2.5 2-2.5 3.5M12 17h.01" /></svg>,
  guide: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 5a2 2 0 012-2h6v18H6a2 2 0 00-2 2z" /><path d="M20 5a2 2 0 00-2-2h-6v18h6a2 2 0 002 2z" /></svg>,
  check: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M5 12l4 4L19 6" /></svg>,
  arrow: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M5 12h14m-6-6l6 6-6 6" /></svg>,
  close: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M6 6l12 12M18 6L6 18" /></svg>,
  search: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></svg>,
  shield: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></svg>,
  alert: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l10 18H2z" /><path d="M12 10v4m0 4h.01" /></svg>,
  logout: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9" /></svg>,
  eye: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>,
  layers: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></svg>,
  file: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4" /></svg>,
  link: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1" /></svg>,
  download: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 4v12m0 0l-4-4m4 4l4-4" /><path d="M4 18v2h16v-2" /></svg>,
  play: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M7 5l12 7-12 7z" /></svg>,
};
