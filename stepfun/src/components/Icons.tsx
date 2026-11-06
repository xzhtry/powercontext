import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "logo"
  | "search"
  | "database"
  | "cpu"
  | "bolt"
  | "upload"
  | "file"
  | "trash"
  | "plus"
  | "sparkles"
  | "shield"
  | "chevron"
  | "close"
  | "copy"
  | "check"
  | "download"
  | "refresh"
  | "alert"
  | "layers"
  | "info"
  | "arrow"
  | "gauge"
  | "terminal"
  | "book"
  | "lock"
  | "globe"
  | "clock";

const paths: Record<IconName, ReactNode> = {
  logo: (
    <>
      <path d="M4 5.5 12 2l8 3.5v13L12 22l-8-3.5z" fill="currentColor" opacity=".16" />
      <path d="M4 5.5 12 2l8 3.5v13L12 22l-8-3.5z" />
      <path d="m8.2 12.1 2.5 2.6 5.1-5.4" />
    </>
  ),
  search: (
    <>
      <circle cx="10.8" cy="10.8" r="6.4" />
      <path d="m15.6 15.6 4.4 4.4" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="3" />
      <path d="M4.5 5.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
      <path d="M4.5 11.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
    </>
  ),
  cpu: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="2.2" />
      <path d="M9.5 2.8v3.7M14.5 2.8v3.7M9.5 17.5v3.7M14.5 17.5v3.7M2.8 9.5h3.7M2.8 14.5h3.7M17.5 9.5h3.7M17.5 14.5h3.7" />
    </>
  ),
  bolt: <path d="M13.5 2.5 5 13.2h5.5l-.8 8.3 8.8-11h-5.7z" />,
  upload: (
    <>
      <path d="M12 16V3.8M7.6 8.2 12 3.8l4.4 4.4" />
      <path d="M4 15.3v3.4c0 1 .8 1.8 1.8 1.8h12.4c1 0 1.8-.8 1.8-1.8v-3.4" />
    </>
  ),
  file: (
    <>
      <path d="M6 2.8h8l4 4v14.4H6z" />
      <path d="M14 2.8v4h4M9 12h6M9 15.5h6M9 19h4" />
    </>
  ),
  trash: (
    <>
      <path d="M4 6.5h16M9 3.5h6l1 3H8zM6.5 6.5l1 14h9l1-14M10 10.5v6M14 10.5v6" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  sparkles: (
    <>
      <path d="m12 2 1.7 5.3L19 9l-5.3 1.7L12 16l-1.7-5.3L5 9l5.3-1.7z" />
      <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8zM5 14l.6 1.7L7.3 16l-1.7.6L5 18.3l-.6-1.7L2.7 16l1.7-.6z" />
    </>
  ),
  shield: (
    <>
      <path d="M12 2.8 20 6v5.2c0 5-3.3 8.4-8 10-4.7-1.6-8-5-8-10V6z" />
      <path d="m8.6 12 2.2 2.2 4.6-4.8" />
    </>
  ),
  chevron: <path d="m6 9 6 6 6-6" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  copy: (
    <>
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V5.8c0-1-.8-1.8-1.8-1.8H5.8C4.8 4 4 4.8 4 5.8v8.4C4 15.2 4.8 16 5.8 16H8" />
    </>
  ),
  check: <path d="m4.5 12.5 4.8 4.8L19.5 7" />,
  download: (
    <>
      <path d="M12 3v13M7.5 11.5 12 16l4.5-4.5" />
      <path d="M4 20h16" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7v5h-5M4 17v-5h5" />
      <path d="M6.1 8.2A7 7 0 0 1 19.8 11M17.9 15.8A7 7 0 0 1 4.2 13" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3 22 21H2z" />
      <path d="M12 9v5M12 17.5v.2" />
    </>
  ),
  layers: (
    <>
      <path d="m12 2.5 9 4.8-9 4.8-9-4.8z" />
      <path d="m3 12 9 4.8 9-4.8M3 16.7l9 4.8 9-4.8" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 10.5v6M12 7.5v.2" />
    </>
  ),
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  gauge: (
    <>
      <path d="M4 18a8 8 0 1 1 16 0" />
      <path d="m12 14 4.5-4.5M6.5 18h11" />
    </>
  ),
  terminal: (
    <>
      <rect x="3" y="4.5" width="18" height="15" rx="2" />
      <path d="m7 9 3 3-3 3M12.5 15H17" />
    </>
  ),
  book: (
    <>
      <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v19H6.5A2.5 2.5 0 0 0 4 23.5z" />
      <path d="M4 4.5v17M8 7h8M8 11h6" />
    </>
  ),
  lock: (
    <>
      <rect x="4.5" y="10" width="15" height="11" rx="2.2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.6 2.5 3.9 5.5 3.9 9S14.6 18.5 12 21c-2.6-2.5-3.9-5.5-3.9-9S9.4 5.5 12 3z" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5.2l3.2 1.8" />
    </>
  ),
};

export function Icon({
  name,
  size = 18,
  ...props
}: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
